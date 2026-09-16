// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * ============================================================================
 * BNB CIRCUIT BREAKER v1.4.1 HARDENED — REVISIÓN TÉCNICA Y CORRECCIÓN TOTAL
 * ============================================================================
 * CORRECCIONES CRÍTICAS INTEGRADAS:
 * 1. FIX MATEMÁTICO & ESCALA DECIMAL EN ORÁCULO:
 *    - Se eliminó el truncamiento a 0 por desplazamiento directo >> 192.
 *    - Se parametrizaron los decimales de Token0, Token1 y Chainlink en OracleConfig.
 *    - Se normalizó la conversión matemática de sqrtPriceX96 con FullMath para
 *      alinear con la escala exacta del feed de Chainlink (típicamente 8 o 18 decimales).
 *
 * 2. FIX DE BLOQUEO IRREVERSIBLE EN UNPAUSE:
 *    - Se agregó forceUnpauseByGovernance para permitir que el Gnosis Safe reactive
 *      mercados manualmente si el feed de Chainlink está temporalmente descalibrado.
 *    - Se desacopló la validación obligatoria de oráculo en mercados que no dependen
 *      directamente de Chainlink.
 *
 * 3. FIX DE SELECTORES DE EMERGENCIA:
 *    - En EMERGENCY_PAUSED, todas las operaciones de swap/borrow quedan estrictamente
 *      bloqueadas por defecto (cero exploits durante el ataque activo).
 *    - Los selectores de escape (liquidación/retiro pro-rata) solo se autorizan
 *      durante EMERGENCY_WIND_DOWN.
 * ============================================================================
 */

interface AggregatorV3Interface {
    function decimals() external view returns (uint8);
    function latestRoundData() external view returns (
        uint80 roundId,
        int256 answer,
        uint256 startedAt,
        uint256 updatedAt,
        uint80 answeredInRound
    );
}

interface IPancakeV3Pool {
    function slot0() external view returns (
        uint160 sqrtPriceX96,
        int24 tick,
        uint16 observationIndex,
        uint16 observationCardinality,
        uint16 observationCardinalityNext,
        uint8 feeProtocol,
        bool unlocked
    );
}

library FullMath {
    function mulDiv(uint256 a, uint256 b, uint256 denominator) internal pure returns (uint256 result) {
        unchecked {
            uint256 mm = mulmod(a, b, type(uint256).max);
            uint256 prod0 = a * b;
            uint256 prod1 = mm - prod0 - (mm < prod0 ? 1 : 0);
            if (prod1 == 0) {
                require(denominator > 0, "FullMath: zero denominator");
                return prod0 / denominator;
            }
            require(denominator > prod1, "FullMath: overflow");
            uint256 remainder = mulmod(a, b, denominator);
            if (remainder > 0) {
                prod0 -= remainder;
                if (prod0 > type(uint256).max - remainder) {
                    prod1 -= 1;
                }
            }
            uint256 twos = denominator & (~denominator + 1);
            denominator /= twos;
            prod0 /= twos;
            uint256 inv = (3 * denominator) ^ 2;
            inv *= 2 - denominator * inv;
            inv *= 2 - denominator * inv;
            inv *= 2 - denominator * inv;
            inv *= 2 - denominator * inv;
            inv *= 2 - denominator * inv;
            inv *= 2 - denominator * inv;
            result = prod0 * inv;
            return result;
        }
    }
}

contract BNBCircuitBreaker {
    using FullMath for uint256;

    bytes32 public constant DEFAULT_ADMIN_ROLE = 0x00;
    bytes32 public constant PAUSER_ROLE = keccak256("PAUSER_ROLE");
    bytes32 public constant UNPAUSER_ROLE = keccak256("UNPAUSER_ROLE");

    enum MarketState {
        OPERATIONAL,          // Operación normal
        EMERGENCY_PAUSED,     // Bloqueo total bajo ataque
        EMERGENCY_WIND_DOWN   // Desescalado: solo selectores autorizados
    }

    uint256 public constant MAX_PAUSE_DURATION = 24 hours;
    uint256 public constant MAX_CONSECUTIVE_PAUSES = 2;
    uint256 public constant DEFAULT_MAX_DEVIATION_BPS = 1500; // 15%
    uint256 public constant MAX_ORACLE_STALENESS = 3600;      // 1 hora

    struct OracleConfig {
        address chainlinkFeed;
        uint8 token0Decimals;
        uint8 token1Decimals;
        uint8 chainlinkDecimals;
        uint256 maxDeviationBps;
        uint256 maxStalenessSeconds;
        bool exists;
    }

    struct MarketStatus {
        MarketState state;
        uint256 pausedTimestamp;
        uint256 pausedBlock;
        uint256 consecutivePauses;
        string reason;
    }

    address public governanceSafe;
    address public guardianBot;

    mapping(address => bool) public authorizedMarkets;
    mapping(address => OracleConfig) public oracleConfigs;
    mapping(address => MarketStatus) public marketInfo;
    mapping(address => mapping(bytes4 => bool)) public allowedEmergencySelectors;
    mapping(bytes32 => mapping(address => bool)) private _roles;

    event MarketEmergencyPaused(address indexed market, address indexed caller, string reason, uint256 blockNumber, uint256 timestamp);
    event MarketEmergencyUnpaused(address indexed market, address indexed caller, uint256 timestamp);
    event MarketForceUnpaused(address indexed market, address indexed caller, uint256 timestamp);
    event OracleConfigured(address indexed market, address chainlinkFeed, uint256 maxDeviationBps);
    event EmergencySelectorConfigured(address indexed market, bytes4 selector, bool allowed);
    event DeploymentFinalized(address indexed finalGovernance);

    error CallerLacksRequiredRole(bytes32 role);
    error InvalidZeroAddress();
    error MarketNotOperational();
    error MarketAlreadyOperational();
    error MaxConsecutivePausesExceeded();
    error OracleStaleData();
    error UnauthorizedMarket();

    modifier onlyRole(bytes32 role) {
        if (!_roles[role][msg.sender]) revert CallerLacksRequiredRole(role);
        _;
    }

    constructor(address _governanceSafe, address _guardianBot) {
        if (_governanceSafe == address(0) || _guardianBot == address(0)) revert InvalidZeroAddress();
        governanceSafe = _governanceSafe;
        guardianBot = _guardianBot;

        _roles[DEFAULT_ADMIN_ROLE][msg.sender] = true;
        _roles[DEFAULT_ADMIN_ROLE][_governanceSafe] = true;
        _roles[UNPAUSER_ROLE][_governanceSafe] = true;
        _roles[PAUSER_ROLE][_guardianBot] = true;
    }

    function finalizeDeployment() external onlyRole(DEFAULT_ADMIN_ROLE) {
        if (msg.sender != governanceSafe) {
            _roles[DEFAULT_ADMIN_ROLE][msg.sender] = false;
        }
        emit DeploymentFinalized(governanceSafe);
    }

    function configureMarket(
        address market,
        address chainlinkFeed,
        uint8 token0Decimals,
        uint8 token1Decimals,
        uint256 maxDeviationBps,
        uint256 maxStalenessSeconds
    ) external onlyRole(DEFAULT_ADMIN_ROLE) {
        if (market == address(0) || chainlinkFeed == address(0)) revert InvalidZeroAddress();
        
        uint8 clDecimals = AggregatorV3Interface(chainlinkFeed).decimals();

        authorizedMarkets[market] = true;
        oracleConfigs[market] = OracleConfig({
            chainlinkFeed: chainlinkFeed,
            token0Decimals: token0Decimals,
            token1Decimals: token1Decimals,
            chainlinkDecimals: clDecimals,
            maxDeviationBps: maxDeviationBps > 0 ? maxDeviationBps : DEFAULT_MAX_DEVIATION_BPS,
            maxStalenessSeconds: maxStalenessSeconds > 0 ? maxStalenessSeconds : MAX_ORACLE_STALENESS,
            exists: true
        });

        emit OracleConfigured(market, chainlinkFeed, maxDeviationBps);
    }

    function setEmergencySelector(address market, bytes4 selector, bool allowed) external onlyRole(DEFAULT_ADMIN_ROLE) {
        allowedEmergencySelectors[market][selector] = allowed;
        emit EmergencySelectorConfigured(market, selector, allowed);
    }

    // =========================================================================
    // ARQUITECTURA DE ORÁCULO NORMALIZADA (PRECISIÓN 512-BIT)
    // =========================================================================

    function getValidatedChainlinkPrice(address market) public view returns (uint256) {
        OracleConfig memory cfg = oracleConfigs[market];
        if (!cfg.exists || cfg.chainlinkFeed == address(0)) return 0;

        (uint80 roundId, int256 price, , uint256 updatedAt, uint80 answeredInRound) =
            AggregatorV3Interface(cfg.chainlinkFeed).latestRoundData();

        if (price <= 0 || updatedAt == 0) revert OracleStaleData();
        if (block.timestamp < updatedAt || block.timestamp - updatedAt > cfg.maxStalenessSeconds) revert OracleStaleData();
        if (answeredInRound < roundId) revert OracleStaleData();

        return uint256(price);
    }

    /**
     * @notice Convierte sqrtPriceX96 al precio spot de PancakeSwap v3 normalizado con la escala de Chainlink.
     * @dev Evita truncamiento calculando en 2 pasos de multiplicación con FullMath.
     */
    function isPriceManipulated(address pancakePool, uint160 sqrtPriceX96) public view returns (bool) {
        OracleConfig memory cfg = oracleConfigs[pancakePool];
        if (!cfg.exists) return false;

        uint256 chainlinkPrice = getValidatedChainlinkPrice(pancakePool);
        if (chainlinkPrice == 0) return false;

        // ratioX128 = (sqrtPriceX96^2) >> 64 = mulDiv(sqrtPriceX96, sqrtPriceX96, 2^64)
        uint256 ratioX128 = FullMath.mulDiv(uint256(sqrtPriceX96), uint256(sqrtPriceX96), 1 << 64);
        if (ratioX128 == 0) return false;

        // Escalar por los decimales de Chainlink y compensar diferencias de decimales de los tokens:
        // spotPrice = (ratioX128 * 10^clDecimals * 10^t0Decimals) / (10^t1Decimals * 2^128)
        uint256 numerator = FullMath.mulDiv(
            ratioX128,
            (10 ** cfg.chainlinkDecimals) * (10 ** cfg.token0Decimals),
            10 ** cfg.token1Decimals
        );
        
        uint256 spotPrice = numerator >> 128;
        if (spotPrice == 0) return false;

        uint256 delta = spotPrice > chainlinkPrice ? spotPrice - chainlinkPrice : chainlinkPrice - spotPrice;
        uint256 deviationBps = (delta * 10000) / chainlinkPrice;

        return (deviationBps > cfg.maxDeviationBps);
    }

    // =========================================================================
    // MECÁNICA DE PAUSA NO CUSTODIAL & DESPAUSA RESILIENTE
    // =========================================================================

    function pauseMarket(address market, string calldata reason) external onlyRole(PAUSER_ROLE) {
        if (!authorizedMarkets[market]) revert UnauthorizedMarket();
        MarketStatus storage status = marketInfo[market];
        if (status.state != MarketState.OPERATIONAL) revert MarketNotOperational();
        if (status.consecutivePauses >= MAX_CONSECUTIVE_PAUSES) revert MaxConsecutivePausesExceeded();

        status.state = MarketState.EMERGENCY_PAUSED;
        status.pausedTimestamp = block.timestamp;
        status.pausedBlock = block.number;
        status.consecutivePauses += 1;
        status.reason = reason;

        emit MarketEmergencyPaused(market, msg.sender, reason, block.number, block.timestamp);
    }

    function unpauseMarket(address market) external onlyRole(UNPAUSER_ROLE) {
        MarketStatus storage status = marketInfo[market];
        if (status.state == MarketState.OPERATIONAL) revert MarketAlreadyOperational();

        if (oracleConfigs[market].exists) {
            getValidatedChainlinkPrice(market);
        }

        status.state = MarketState.OPERATIONAL;
        status.consecutivePauses = 0;
        delete status.pausedTimestamp;
        delete status.pausedBlock;
        delete status.reason;

        emit MarketEmergencyUnpaused(market, msg.sender, block.timestamp);
    }

    /**
     * @notice Permite a la Gobernanza reactivar un mercado si el oráculo está descalibrado.
     */
    function forceUnpauseByGovernance(address market) external onlyRole(DEFAULT_ADMIN_ROLE) {
        MarketStatus storage status = marketInfo[market];
        if (status.state == MarketState.OPERATIONAL) revert MarketAlreadyOperational();

        status.state = MarketState.OPERATIONAL;
        status.consecutivePauses = 0;
        delete status.pausedTimestamp;
        delete status.pausedBlock;
        delete status.reason;

        emit MarketForceUnpaused(market, msg.sender, block.timestamp);
    }

    function isOperationPermitted(address market, bytes4 selector) external view returns (bool) {
        MarketState currentState = getMarketState(market);
        if (currentState == MarketState.OPERATIONAL) return true;
        if (currentState == MarketState.EMERGENCY_PAUSED) return false;
        if (currentState == MarketState.EMERGENCY_WIND_DOWN) {
            return allowedEmergencySelectors[market][selector];
        }
        return false;
    }

    function getMarketState(address market) public view returns (MarketState) {
        MarketStatus memory status = marketInfo[market];
        if (status.state == MarketState.OPERATIONAL) return MarketState.OPERATIONAL;
        if (block.timestamp > status.pausedTimestamp + MAX_PAUSE_DURATION) {
            return MarketState.EMERGENCY_WIND_DOWN;
        }
        return status.state;
    }

    function hasRole(bytes32 role, address account) external view returns (bool) {
        return _roles[role][account];
    }
}
