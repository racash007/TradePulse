# TradePulse 📈

A sophisticated Python-based trading system that combines technical analysis strategies (FVG Order Blocks and Sonarlab Order Blocks) with intelligent risk management, backtesting capabilities, and both paper and live trading execution.

## 🌟 Features

- **Advanced Trading Strategies**
  - FVG (Fair Value Gap) Order Blocks analysis
  - Sonarlab Order Blocks integration
  - Signal strength classification and scoring
  - Multi-indicator overlap detection

- **Risk Management**
  - Dynamic capital allocation based on signal strength
  - Configurable stop-loss and take-profit targets
  - Position sizing with allocation steps
  - Force close capability for open positions

- **Trading Modes**
  - **Paper Trading**: Simulate trades without real capital
  - **Live Trading**: Execute real trades via broker API integration
  - **Backtesting**: Historical strategy performance analysis

- **Interactive UI**
  - Streamlit-based web interface
  - Real-time chart visualization with candlesticks
  - Signal overlays and order block visualization
  - Multi-security backtesting with parallel processing
  - Portfolio performance tracking and analytics

## 📋 Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Trading Strategy](#trading-strategy)
- [Project Structure](#project-structure)
- [Usage](#usage)
- [Configuration](#configuration)
- [Testing](#testing)
- [Contributing](#contributing)

## 🚀 Installation

### Prerequisites

- Python 3.8 or higher
- pip package manager

### Setup

1. Clone the repository:
```bash
git clone https://github.com/ashitoshshinde46/TradePulse.git
cd TradePulse
```

2. Install required dependencies:
```bash
pip install -r requirements.txt
```

### Dependencies

The project requires the following packages:
- `pandas` - Data manipulation and analysis
- `numpy` - Numerical computations
- `matplotlib` - Chart plotting and visualization
- `streamlit` - Web UI framework
- `flask[async]>=2.2` - API and webhook support
- `pytest` - Testing framework

## 🎯 Quick Start

### Running the Application

Launch the Streamlit web interface:

```bash
streamlit run app/application.py
```

The application will open in your default browser at `http://localhost:8501`

### Basic Workflow

1. **Select Data**: Choose a CSV file from the sidebar containing OHLC (Open, High, Low, Close) data
2. **Configure Parameters**:
   - Initial Capital: Starting capital for trading
   - Target %: Take-profit percentage (default: 7%)
   - Stop Loss %: Stop-loss percentage (default: 3%)
   - Allocation Step: Capital allocation per signal strength unit (default: 20%)

3. **Choose Mode**:
   - **Viewer Tab**: Real-time signal generation and visualization
   - **Backtest Tab**: Historical performance analysis across multiple securities

## 📊 Trading Strategy

### Signal Generation

The system uses two complementary strategies:

#### 1. FVG Order Blocks [BigBeluga]
- Detects Fair Value Gaps (imbalances) in price action
- Identifies bullish and bearish order blocks
- Filters signals based on gap size relative to ATR (Average True Range)

#### 2. Sonarlab Order Blocks
- Identifies institutional order blocks
- Tracks support and resistance zones
- Validates signal quality through zone analysis

### Entry Conditions

**Long (Buy) Setup:**
- ✅ "︽" Buy signal appears from FVG Order Blocks
- ✅ Signal candle lies inside a bullish FVG zone OR bullish Order Block
- ✅ Entry on signal candle close or next open

**Short (Sell) Setup:**
- ✅ "﹀" Sell signal appears from FVG Order Blocks
- ✅ Signal candle lies inside a bearish FVG zone OR bearish Order Block
- ✅ Entry on signal candle close or next open

### Exit Conditions

**Take Profit:**
- Conservative: 2% from entry price
- Aggressive: 3% from entry price (default: 7% in system)

**Stop Loss:**
- Long: 0.1% below Order Block boundary
- Short: 0.1% above Order Block boundary
- Default system: 3% from entry

### Signal Strength Classification

Signals are classified into 5 strength levels based on:
- Number of indicator overlaps (FVG + Sonarlab)
- Risk-reward ratio
- Order block quality

Capital allocation scales with signal strength (1-5), where:
- Strength 1 = 20% of base allocation
- Strength 5 = 100% of base allocation

## 📁 Project Structure

```
TradePulse/
├── app/
│   ├── agent/              # Trading agents and signal processors
│   │   ├── agent.py        # Base agent interface
│   │   ├── paper_trade_agent.py   # Paper trading implementation
│   │   ├── trade_agent.py         # Live trading with broker
│   │   ├── signal_generator.py    # Signal generation logic
│   │   ├── signal_processor.py    # Signal processing pipeline
│   │   └── signal_strength.py     # Signal strength classifier
│   │
│   ├── model/              # Data models
│   │   ├── box.py          # Order block box representation
│   │   ├── signal.py       # Signal model
│   │   ├── trade.py        # Trade execution model
│   │   ├── portfolio.py    # Portfolio tracking
│   │   └── OutcomeType.py  # Trade outcome enums
│   │
│   ├── strategy/           # Trading strategies
│   │   ├── fvgorderblocks.py           # FVG Order Blocks strategy
│   │   ├── sonarlaplaceorderblocks.py  # Sonarlab strategy
│   │   └── strategy.py                 # Base strategy interface
│   │
│   ├── service/            # External services
│   │   └── broker_service.py  # Broker API integration
│   │
│   ├── ui/                 # User interface components
│   │   ├── backtest.py     # Backtesting UI
│   │   ├── viewer.py       # Real-time viewer UI
│   │   ├── common.py       # Shared UI components
│   │   └── signal_utils.py # Signal display utilities
│   │
│   ├── utility/            # Utility functions
│   │   ├── plot_utils.py   # Chart plotting helpers
│   │   ├── signal_util.py  # Signal processing utils
│   │   ├── file_util.py    # File operations
│   │   └── utility.py      # General utilities
│   │
│   ├── application.py      # Main Streamlit application
│   └── broker_application.py  # Broker-specific app
│
├── resource/
│   ├── data/               # Live trading data
│   └── backtest_data/      # Historical data for backtesting
│
├── tests/                  # Test suite
│   ├── test_trade_agent.py
│   ├── test_paper_trade_agent.py
│   ├── test_signal_generator.py
│   └── smoke_trade_agent.py
│
├── requirements.txt        # Python dependencies
├── README.md              # This file
└── Risk Management and Strategy rules.txt  # Detailed strategy rules
```

## 💻 Usage

### Paper Trading

Paper trading allows you to test strategies without risking real capital:

```python
from agent.paper_trade_agent import PaperTradeAgent
from agent.signal_generator import SignalGenerator

# Initialize paper trading agent
agent = PaperTradeAgent(
    initial_capital=100000.0,
    target_pct=0.07,
    stop_loss_pct=0.03,
    allocation_step=0.2
)

# Generate and execute signals
signal_gen = SignalGenerator()
signals = signal_gen.generate_signals(df, symbol="INFY")
trades = agent.execute_signals(df, signals)
```

### Live Trading

Live trading requires broker configuration:

```python
from agent.trade_agent import TradeAgent
from service.broker_service import BrokerConfig

# Configure broker
broker_config = BrokerConfig(
    api_key="your_api_key",
    access_token="your_access_token"
)

# Initialize live trading agent
agent = TradeAgent(
    broker_config=broker_config,
    exchange='NSE',
    product='CNC',
    initial_capital=100000.0
)

# Execute signals with real orders
trades = agent.execute_signals(df, signals)
```

### Backtesting

Run backtests across multiple securities:

1. Place CSV files in `resource/backtest_data/`
2. Launch the application
3. Navigate to the "Back Test" tab
4. Select securities to test
5. Click "Run Backtest"

The system will:
- Process each security in parallel
- Generate signals using both strategies
- Execute trades according to rules
- Display comprehensive performance metrics

## ⚙️ Configuration

### Strategy Parameters

Adjust in the UI sidebar or programmatically:

- **Initial Capital**: Starting portfolio value (default: ₹100,000)
- **Target %**: Take-profit percentage (default: 7%)
- **Stop Loss %**: Maximum loss per trade (default: 3%)
- **Allocation Step**: Capital allocation per strength unit (default: 0.2)

### Data Format

CSV files should contain OHLC data with columns:
```
Date, Open, High, Low, Close, Volume (optional)
```

Expected filename format:
```
DD-MM-YYYY-TO-DD-MM-YYYY-SYMBOL-EQ-N.csv
```

Example: `01-11-2024-TO-01-11-2025-INFY-EQ-N.csv`

## 🧪 Testing

Run the test suite:

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_trade_agent.py

# Run with verbose output
pytest -v

# Run smoke tests
python tests/smoke_trade_agent.py
```

### Test Coverage

- `test_trade_agent.py`: Live trading agent functionality
- `test_paper_trade_agent.py`: Paper trading simulation
- `test_signal_generator.py`: Signal generation logic
- `test_force_close.py`: Position closing mechanisms

## 📈 Performance Metrics

The system tracks and displays:

- **Portfolio Value**: Current total portfolio worth
- **Total Trades**: Number of executed trades
- **Win Rate**: Percentage of profitable trades
- **Profit/Loss**: Absolute and percentage returns
- **Average Trade**: Mean profit/loss per trade
- **Sharpe Ratio**: Risk-adjusted return metric
- **Max Drawdown**: Largest peak-to-trough decline

## 🔧 Broker Integration

The system supports broker API integration for live trading. Configure your broker credentials:

```python
broker_config = BrokerConfig(
    api_key="your_api_key",
    api_secret="your_api_secret",
    access_token="your_access_token",
    broker_name="your_broker"  # e.g., "zerodha", "upstox"
)
```

**Security Note**: Never commit credentials to version control. Use environment variables or secure configuration files.

## 🤝 Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Guidelines

- Follow PEP 8 style guidelines
- Write unit tests for new features
- Update documentation as needed
- Ensure all tests pass before submitting PR

## 📝 License

This project is provided as-is for educational and research purposes.

## ⚠️ Disclaimer

**IMPORTANT**: This software is for educational purposes only. Trading stocks and securities involves substantial risk of loss. Past performance is not indicative of future results. Always conduct your own research and consult with qualified financial advisors before making investment decisions.

The developers and contributors of TradePulse are not responsible for any financial losses incurred through the use of this software.

## 📧 Contact

Project Link: [https://github.com/ashitoshshinde46/TradePulse](https://github.com/ashitoshshinde46/TradePulse)

---

**Built with ❤️ for algorithmic traders**
