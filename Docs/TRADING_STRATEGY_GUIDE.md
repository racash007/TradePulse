# TradePulse Trading Strategy Guide 📚

A comprehensive guide to understanding the trading strategies, concepts, and mechanics used in TradePulse.

## Table of Contents

1. [Introduction](#introduction)
2. [Core Concepts](#core-concepts)
3. [Strategy Components](#strategy-components)
4. [Signal Generation Process](#signal-generation-process)
5. [Risk Management](#risk-management)
6. [Trade Execution](#trade-execution)
7. [Practical Examples](#practical-examples)
8. [Strategy Optimization](#strategy-optimization)
9. [Common Pitfalls](#common-pitfalls)

---

## Introduction

TradePulse implements a **multi-indicator confluence strategy** that combines two powerful technical analysis tools:

1. **FVG (Fair Value Gap) Order Blocks** - Detects price imbalances
2. **Sonarlab Order Blocks** - Identifies institutional support/resistance zones

The strategy seeks **high-probability trade setups** where multiple indicators align, indicating strong institutional interest and potential price reversals.

### Philosophy

> "Trade less, but trade better. Quality over quantity."

The system prioritizes signal quality through:
- Multi-timeframe analysis
- Indicator confluence
- Risk-reward optimization
- Systematic position sizing

---

## Core Concepts

### 1. Fair Value Gap (FVG)

**What is it?**
A Fair Value Gap is a price inefficiency that occurs when there's a sharp price movement leaving an "imbalance" or "gap" in the market.

**How to identify:**
- **Bullish FVG**: When the high of candle [i-2] is below the low of candle [i]
- **Bearish FVG**: When the low of candle [i-2] is above the high of candle [i]

```
Bullish FVG Example:
┌─────┐
│  3  │ ← Current candle (i)
│     │
└─────┘
   ↑ GAP (imbalance - price skipped this area)
┌─────┐
│  2  │ ← Middle candle
└─────┘
   ↑ GAP continues
┌─────┐
│  1  │ ← Two candles ago (i-2)
└─────┘
```

**Why it matters:**
- Represents unfilled orders at certain price levels
- Market often revisits these zones to "fill the gap"
- Acts as potential support (bullish FVG) or resistance (bearish FVG)

**TradePulse Implementation:**
```python
# Bullish FVG Detection
if df['Low'][i] - df['High'][i-2] > 0:
    gap_size = (df['Low'][i] - df['High'][i-2]) / df['Low'][i] * 100
    if gap_size > filter_threshold:
        # Valid Bullish FVG detected
```

### 2. Order Blocks (OB)

**What is it?**
Order Blocks are zones where institutional traders (banks, hedge funds) place large orders, creating significant support or resistance.

**Characteristics:**
- Created by a strong directional move
- Preceded by a consolidation or setup candle
- Represents the last bearish candle before a bullish move (or vice versa)

**Types:**
- **Bullish OB**: Last red candle before strong upward move
- **Bearish OB**: Last green candle before strong downward move

```
Bullish Order Block:
        ┌─────┐
        │  ↑  │  Strong bullish move
        │  ↑  │
        └─────┘
        ┌─────┐
        │  ↑  │
        └─────┘
███████████████  ← BULLISH ORDER BLOCK (last bearish candle)
        ┌─────┐     Zone where institutions bought
        │  ↓  │
        └─────┘
```

**Why it matters:**
- Institutional traders defend these zones
- Price often respects these levels on retests
- High probability of bounce/rejection

### 3. Average True Range (ATR)

**What is it?**
ATR measures market volatility by calculating the average range of price movement over a period (typically 14-200 candles).

**Formula:**
```
True Range = Max of:
- Current High - Current Low
- |Current High - Previous Close|
- |Current Low - Previous Close|

ATR = Moving Average of True Range over N periods
```

**Why it matters:**
- Used to filter out insignificant price gaps
- Helps set dynamic stop-loss levels
- Normalizes signal strength across different volatility regimes

**TradePulse Usage:**
- Filters FVG gaps: Must be > 0.5 * ATR to be considered valid
- Ensures signals are meaningful relative to current market volatility

### 4. Signal Strength Classification

Signals are scored from 1 (weakest) to 5 (strongest) based on:

| Strength | Description | Characteristics | Capital Allocation |
|----------|-------------|----------------|-------------------|
| **5** 🔥 | Very Strong | Both FVG + Sonarlab OB overlap, optimal RR ratio | 100% |
| **4** 💪 | Strong | FVG + Sonarlab OB overlap, good RR ratio | 80% |
| **3** ✅ | Moderate | Single indicator with strong characteristics | 60% |
| **2** ⚠️ | Weak | Single indicator with moderate characteristics | 40% |
| **1** 🤏 | Very Weak | Marginal setup, low confidence | 20% |

**Calculation Factors:**
```python
strength_score = 0

# Factor 1: Indicator Overlap
if fvg_signal and sonarlab_signal:
    strength_score += 2

# Factor 2: Risk-Reward Ratio
if risk_reward_ratio > 2:
    strength_score += 1
elif risk_reward_ratio > 1.5:
    strength_score += 0.5

# Factor 3: Order Block Quality
if ob_volume_confirmed:
    strength_score += 1

# Factor 4: Zone Confluence
if price_near_multiple_zones:
    strength_score += 0.5

# Final: Normalize to 1-5 scale
final_strength = clamp(round(strength_score), 1, 5)
```

---

## Strategy Components

### Component 1: FVG Order Blocks [BigBeluga]

**Parameters:**
- `lookback = 2000`: How far back to analyze
- `filter_gap = 0.5`: Minimum gap size relative to ATR
- `box_amount = 6`: Maximum concurrent order blocks to track
- `ATR period = 200`: Volatility calculation period

**Signal Logic:**

```
Bullish Signal Generated When:
1. Valid Bullish FVG detected (gap > filter_threshold)
2. Price enters or touches the FVG zone
3. No recent invalidation (price hasn't traded significantly below)
4. Signal candle shows bullish characteristics

Bearish Signal Generated When:
1. Valid Bearish FVG detected
2. Price enters or touches the FVG zone
3. No recent invalidation (price hasn't traded significantly above)
4. Signal candle shows bearish characteristics
```

**Zone Management:**
- Up to 6 zones tracked simultaneously
- Older zones removed when new ones appear
- Zones invalidated if price moves too far away
- Broken zones optionally hidden

### Component 2: Sonarlab Order Blocks

**Parameters:**
- Detects institutional accumulation/distribution zones
- Tracks support and resistance levels
- Validates zone strength through retests

**Signal Logic:**

```
Bullish OB Identified When:
1. Strong upward price movement occurs
2. Last bearish candle before move marked as OB
3. Zone remains unbroken (not traded below significantly)

Bearish OB Identified When:
1. Strong downward price movement occurs
2. Last bullish candle before move marked as OB
3. Zone remains unbroken (not traded above significantly)
```

**Zone Validation:**
- First touch: Establishes the zone
- Second touch: Confirms the zone strength
- Multiple rejections: High-confidence zone

### Component 3: Signal Confluence Engine

**How Signals Combine:**

```python
def generate_enhanced_signal(fvg_signal, sonar_signal, price_data):
    """
    Combines signals from both strategies
    """
    # Case 1: Both indicators agree (STRONGEST)
    if fvg_signal.type == sonar_signal.type:
        if zones_overlap(fvg_signal.zone, sonar_signal.zone):
            return Signal(
                type=fvg_signal.type,
                strength=5,
                confidence="VERY HIGH"
            )
    
    # Case 2: FVG signal in Sonarlab zone
    if price_in_zone(fvg_signal.price, sonar_signal.zone):
        return Signal(
            type=fvg_signal.type,
            strength=4,
            confidence="HIGH"
        )
    
    # Case 3: Single indicator only
    return Signal(
        type=fvg_signal.type,
        strength=3,
        confidence="MODERATE"
    )
```

---

## Signal Generation Process

### Step-by-Step Workflow

#### Phase 1: Data Preparation
```
1. Load OHLC data (Open, High, Low, Close, Volume)
2. Calculate ATR(200) for volatility normalization
3. Initialize both strategy engines (FVG + Sonarlab)
4. Set up zone tracking arrays
```

#### Phase 2: Historical Analysis
```
For each candle in chronological order:
    ├─ FVG Strategy:
    │   ├─ Check for Bullish FVG (current_low > prev2_high)
    │   ├─ Check for Bearish FVG (current_high < prev2_low)
    │   ├─ Calculate gap size relative to ATR
    │   ├─ Filter: Keep only gaps > 0.5 * ATR
    │   └─ Create/update FVG zones
    │
    └─ Sonarlab Strategy:
        ├─ Detect strong directional moves
        ├─ Identify setup candles before moves
        ├─ Mark order block zones
        └─ Track zone validity
```

#### Phase 3: Zone Management
```
Active Zone Tracking:
├─ Monitor up to 6 zones per strategy
├─ Update zone boundaries as price evolves
├─ Mark zones as "broken" if invalidated
├─ Remove old/irrelevant zones
└─ Calculate zone confluence scores
```

#### Phase 4: Signal Generation
```
For each new candle:
    ├─ Check if price interacts with any zone
    ├─ Evaluate zone quality and confluence
    ├─ Calculate risk-reward ratio
    ├─ Determine signal strength (1-5)
    ├─ Generate Signal object
    └─ Add to signal list
```

#### Phase 5: Signal Enhancement
```
For each raw signal:
    ├─ Cross-reference with other strategy signals
    ├─ Check for multi-indicator confluence
    ├─ Adjust strength score based on overlaps
    ├─ Calculate optimal entry/exit prices
    └─ Output enhanced signal with metadata
```

### Visual Signal Flow

```
┌──────────────┐
│  OHLC Data   │
└──────┬───────┘
       │
       ├─────────────────┬────────────────┐
       ▼                 ▼                ▼
┌─────────────┐   ┌─────────────┐   ┌─────────┐
│ FVG Strategy│   │   Sonarlab  │   │   ATR   │
│   Engine    │   │   Strategy  │   │ Filter  │
└──────┬──────┘   └──────┬──────┘   └────┬────┘
       │                 │                │
       └────────┬────────┴────────────────┘
                ▼
       ┌─────────────────┐
       │    Confluence   │
       │     Engine      │
       └────────┬────────┘
                ▼
       ┌─────────────────┐
       │     Signal      │
       │  Strength Calc  │
       └────────┬────────┘
                ▼
       ┌─────────────────┐
       │ Enhanced Signal │
       │   (1-5 rating)  │
       └─────────────────┘
```

---

## Risk Management

### Position Sizing Formula

```python
def calculate_position_size(capital, signal_strength, allocation_step, price):
    """
    Dynamic position sizing based on signal quality
    """
    # Base allocation percentage
    base_allocation = allocation_step  # Default: 0.2 (20%)
    
    # Scale by signal strength (1-5)
    strength_multiplier = signal_strength / 5.0
    
    # Calculate allocation amount
    allocation_amount = capital * base_allocation * strength_multiplier
    
    # Convert to shares
    shares = int(allocation_amount / price)
    
    return shares

# Example:
# Capital: ₹100,000
# Signal Strength: 4
# Allocation Step: 0.2
# Price: ₹500
#
# allocation = 100,000 * 0.2 * (4/5) = ₹16,000
# shares = 16,000 / 500 = 32 shares
```

### Stop Loss Strategy

**Two-Tier Stop Loss System:**

#### 1. Initial Stop Loss
```python
def calculate_stop_loss(entry_price, signal_type, ob_boundary, default_sl_pct=0.03):
    """
    Set stop loss based on order block boundary or percentage
    """
    if signal_type == BUY:
        # Long position: Stop below OB boundary
        ob_stop = ob_boundary * 0.999  # 0.1% below
        pct_stop = entry_price * (1 - default_sl_pct)  # 3% below
        
        # Use the higher (less aggressive) stop
        return max(ob_stop, pct_stop)
    
    else:  # SELL
        # Short position: Stop above OB boundary
        ob_stop = ob_boundary * 1.001  # 0.1% above
        pct_stop = entry_price * (1 + default_sl_pct)  # 3% above
        
        # Use the lower (less aggressive) stop
        return min(ob_stop, pct_stop)
```

#### 2. Trailing Stop Loss
```python
def update_trailing_stop(current_price, entry_price, current_stop, signal_type):
    """
    Move stop loss to lock in profits
    """
    if signal_type == BUY:
        # Calculate profit percentage
        profit_pct = (current_price - entry_price) / entry_price
        
        if profit_pct > 0.05:  # 5% profit
            # Move stop to breakeven
            return max(current_stop, entry_price)
        
        elif profit_pct > 0.10:  # 10% profit
            # Trail stop at 5% below current price
            return max(current_stop, current_price * 0.95)
    
    # Similar logic for short positions
```

### Take Profit Strategy

**Multi-Target Approach:**

```python
def calculate_take_profit_levels(entry_price, signal_type, signal_strength):
    """
    Set multiple profit targets based on signal quality
    """
    # Base target percentages
    if signal_strength >= 4:
        targets = [0.03, 0.05, 0.07]  # 3%, 5%, 7%
    elif signal_strength >= 3:
        targets = [0.02, 0.04, 0.06]  # 2%, 4%, 6%
    else:
        targets = [0.02, 0.03, 0.05]  # 2%, 3%, 5%
    
    profit_levels = []
    
    if signal_type == BUY:
        for target in targets:
            profit_levels.append(entry_price * (1 + target))
    else:  # SELL
        for target in targets:
            profit_levels.append(entry_price * (1 - target))
    
    return profit_levels

# Execution strategy:
# - Close 33% of position at Target 1
# - Close 33% at Target 2
# - Close remaining 34% at Target 3 (or trail stop)
```

### Risk-Reward Ratio

```python
def calculate_risk_reward(entry, stop_loss, take_profit):
    """
    Calculate risk-reward ratio for the trade
    """
    risk = abs(entry - stop_loss)
    reward = abs(take_profit - entry)
    
    if risk == 0:
        return 0
    
    return reward / risk

# Minimum acceptable RR ratio: 1.5:1
# Preferred RR ratio: 2:1 or higher
# Excellent RR ratio: 3:1 or higher
```

### Maximum Drawdown Protection

```python
def check_drawdown_limit(current_capital, peak_capital, max_drawdown=0.20):
    """
    Halt trading if drawdown exceeds threshold
    """
    drawdown = (peak_capital - current_capital) / peak_capital
    
    if drawdown > max_drawdown:
        # Trigger drawdown protection
        return {
            'status': 'HALT_TRADING',
            'message': f'Maximum drawdown of {max_drawdown*100}% exceeded',
            'current_drawdown': drawdown,
            'recommendation': 'Review strategy and market conditions'
        }
    
    return {'status': 'OK'}
```

---

## Trade Execution

### Entry Rules

#### Long Entry (Buy)
```
✅ Pre-Entry Checklist:
1. Bullish FVG signal detected ("︽" symbol)
2. Signal candle lies inside:
   - Bullish FVG zone, OR
   - Bullish Sonarlab Order Block
3. Signal strength ≥ 3 (moderate or higher)
4. Risk-reward ratio ≥ 1.5:1
5. No conflicting bearish signals
6. Sufficient capital available

Entry Timing:
- Option A: Market order at close of signal candle
- Option B: Limit order at open of next candle
- Option C: Limit order at FVG zone boundary (more conservative)
```

#### Short Entry (Sell)
```
✅ Pre-Entry Checklist:
1. Bearish FVG signal detected ("﹀" symbol)
2. Signal candle lies inside:
   - Bearish FVG zone, OR
   - Bearish Sonarlab Order Block
3. Signal strength ≥ 3 (moderate or higher)
4. Risk-reward ratio ≥ 1.5:1
5. No conflicting bullish signals
6. Sufficient capital available

Entry Timing:
- Option A: Market order at close of signal candle
- Option B: Limit order at open of next candle
- Option C: Limit order at FVG zone boundary (more conservative)
```

### Exit Rules

#### Take Profit Exits
```python
# System automatically closes positions when:
1. Price reaches Target 1 (typically +2-3%)
   → Close 33% of position
   → Move stop loss to breakeven

2. Price reaches Target 2 (typically +4-5%)
   → Close another 33% of position
   → Trail stop loss to Target 1 level

3. Price reaches Target 3 (typically +6-7%)
   → Close remaining position
   → Lock in full profit
```

#### Stop Loss Exits
```python
# System closes position immediately when:
1. Price hits initial stop loss level
   → Close 100% of position
   → Log as stop-loss exit

2. Opposing signal appears (signal reversal)
   → Close 100% of position
   → Potential re-entry in opposite direction

3. End-of-day/period (if configured)
   → Close 100% of open positions
   → Prevents overnight risk
```

#### Time-Based Exits
```python
# Optional: Close position after N days
max_hold_period = 10  # days

if (current_date - entry_date).days > max_hold_period:
    if position_profit > 0:
        # Close profitable position
        close_position("TIME_EXIT_PROFIT")
    else:
        # Evaluate: hold or close at small loss
        if position_profit < -0.01:  # More than 1% loss
            close_position("TIME_EXIT_LOSS")
```

### Trade Management

#### Position Monitoring
```python
def monitor_position(trade, current_price, current_date):
    """
    Check position status and take actions
    """
    # Calculate current P&L
    if trade.side == BUY:
        pnl_pct = (current_price - trade.entry_price) / trade.entry_price
    else:
        pnl_pct = (trade.entry_price - current_price) / trade.entry_price
    
    # Check stop loss
    if should_stop_out(current_price, trade.stop_loss, trade.side):
        return close_position(trade, current_price, "STOP_LOSS")
    
    # Check take profit
    for i, target in enumerate(trade.take_profit_levels):
        if target_hit(current_price, target, trade.side):
            return partial_close(trade, current_price, f"TARGET_{i+1}")
    
    # Update trailing stop
    if pnl_pct > 0.05:  # 5% profit
        trade.stop_loss = update_trailing_stop(
            current_price, 
            trade.entry_price,
            trade.stop_loss,
            trade.side
        )
    
    return "HOLD"
```

---

## Practical Examples

### Example 1: High-Strength Buy Signal

**Setup:**
```
Symbol: INFY (Infosys)
Date: January 5, 2025
Current Price: ₹1,450
ATR(200): ₹15

Detected:
- Bullish FVG from ₹1,440 to ₹1,445
- Sonarlab Bullish OB from ₹1,438 to ₹1,447
- Zones overlap significantly

Signal Strength: 5 (Very Strong)
```

**Trade Calculation:**
```python
# Capital Allocation
portfolio_capital = 100,000
allocation_step = 0.2
signal_strength = 5

allocation = 100,000 * 0.2 * (5/5) = ₹20,000
shares = 20,000 / 1,450 = 13 shares

# Entry
entry_price = 1,450

# Stop Loss (0.1% below OB boundary at ₹1,438)
stop_loss = 1,438 * 0.999 = ₹1,436.56

# Take Profit Targets
target_1 = 1,450 * 1.03 = ₹1,493.50  (3%)
target_2 = 1,450 * 1.05 = ₹1,522.50  (5%)
target_3 = 1,450 * 1.07 = ₹1,551.50  (7%)

# Risk-Reward
risk = 1,450 - 1,436.56 = ₹13.44 per share
reward = 1,551.50 - 1,450 = ₹101.50 per share
RR_ratio = 101.50 / 13.44 = 7.55:1 ✅ Excellent!
```

**Trade Execution:**
```
Day 1 (Jan 5): Enter long 13 shares @ ₹1,450
Day 2 (Jan 6): Price reaches ₹1,495 → Close 4 shares @ Target 1
                Move stop loss to breakeven (₹1,450)
Day 3 (Jan 7): Price reaches ₹1,525 → Close 4 shares @ Target 2
                Trail stop to ₹1,493
Day 5 (Jan 9): Price reaches ₹1,555 → Close 5 shares @ Target 3

Results:
- Total entry: 13 × ₹1,450 = ₹18,850
- Total exit: (4 × ₹1,495) + (4 × ₹1,525) + (5 × ₹1,555) = ₹19,855
- Profit: ₹1,005 (5.3% return)
- Hold period: 5 days
```

### Example 2: Moderate-Strength Sell Signal

**Setup:**
```
Symbol: TCS (Tata Consultancy Services)
Date: February 10, 2025
Current Price: ₹3,200
ATR(200): ₹40

Detected:
- Bearish FVG from ₹3,210 to ₹3,215
- No Sonarlab OB overlap
- Single indicator only

Signal Strength: 3 (Moderate)
```

**Trade Calculation:**
```python
# Capital Allocation (reduced due to lower strength)
allocation = 100,000 * 0.2 * (3/5) = ₹12,000
shares = 12,000 / 3,200 = 3 shares

# Entry
entry_price = 3,200

# Stop Loss (0.1% above OB boundary at ₹3,215)
stop_loss = 3,215 * 1.001 = ₹3,218.22

# Take Profit Targets (conservative for moderate signal)
target_1 = 3,200 * 0.98 = ₹3,136  (2%)
target_2 = 3,200 * 0.96 = ₹3,072  (4%)
target_3 = 3,200 * 0.94 = ₹3,008  (6%)

# Risk-Reward
risk = 3,218.22 - 3,200 = ₹18.22 per share
reward = 3,200 - 3,008 = ₹192 per share
RR_ratio = 192 / 18.22 = 10.54:1 ✅ Excellent!
```

**Trade Execution:**
```
Day 1 (Feb 10): Enter short 3 shares @ ₹3,200
Day 1 (Feb 10): Price immediately moves against us to ₹3,218
                Stop loss triggered → Close 3 shares @ ₹3,218

Results:
- Total entry: 3 × ₹3,200 = ₹9,600
- Total exit: 3 × ₹3,218 = ₹9,654
- Loss: ₹54 (0.56% loss)
- Hold period: 1 day

Lesson: Even with good RR ratio, moderate signals have lower
        win rate. Stop loss protected capital from larger loss.
```

### Example 3: Signal Rejection (No Trade)

**Setup:**
```
Symbol: TITAN (Titan Company)
Date: March 15, 2025
Current Price: ₹2,850
ATR(200): ₹30

Detected:
- Bullish FVG from ₹2,845 to ₹2,848 (gap = ₹3)
- Gap size: 3/2850 = 0.105% of price
- Relative to ATR: 3/30 = 0.10 (10% of ATR)

Signal Strength: Would be 2, but...
```

**Signal Rejection Reason:**
```python
# Filter check
gap_size = 3
atr = 30
filter_threshold = 0.5  # 50% of ATR

if gap_size < (atr * filter_threshold):
    # 3 < (30 * 0.5) = 3 < 15
    reject_signal("Gap too small relative to volatility")

Result: ❌ Signal REJECTED - does not meet minimum criteria
        No trade executed
        
Lesson: Not every potential signal becomes an actual trade.
        Filters protect against low-quality setups.
```

---

## Strategy Optimization

### Parameter Tuning

#### ATR Period
```
Default: 200 candles

Shorter (50-100):
+ More responsive to recent volatility
+ Better for trending markets
- More false signals in choppy markets

Longer (200-300):
+ Smoother filtering
+ Better for ranging markets
- May miss quick volatility changes

Recommendation: Start with 200, adjust based on market regime
```

#### Filter Gap Threshold
```
Default: 0.5 (50% of ATR)

Lower (0.3-0.4):
+ More signals generated
+ May catch smaller opportunities
- Higher noise, more false signals

Higher (0.6-0.8):
+ Fewer, higher-quality signals
+ Better win rate
- May miss valid opportunities

Recommendation: 0.5 for balanced approach
```

#### Allocation Step
```
Default: 0.2 (20%)

Lower (0.1-0.15):
+ More conservative
+ Better for risk-averse traders
- Slower capital growth

Higher (0.25-0.3):
+ More aggressive
+ Faster capital growth potential
- Higher drawdown risk

Recommendation: 0.2 for moderate risk tolerance
```

### Backtesting Insights

**What to Look For:**

1. **Win Rate**
   - Target: 50-60% for this strategy
   - Below 45%: Parameters may need adjustment
   - Above 70%: May be overfitted, verify on new data

2. **Profit Factor**
   ```
   Profit Factor = Gross Profit / Gross Loss
   
   > 2.0: Excellent
   1.5-2.0: Good
   1.0-1.5: Marginal
   < 1.0: Losing strategy
   ```

3. **Sharpe Ratio**
   ```
   Sharpe = (Return - Risk-free Rate) / Standard Deviation
   
   > 2.0: Excellent
   1.0-2.0: Good
   0.5-1.0: Acceptable
   < 0.5: Poor risk-adjusted returns
   ```

4. **Maximum Drawdown**
   - Target: < 15% of peak capital
   - Warning: 15-25%
   - Critical: > 25% (requires strategy revision)

5. **Average Trade Duration**
   - Ideal: 3-7 days
   - Too short (< 2 days): May need better filters
   - Too long (> 10 days): May need tighter exits

### Market Regime Adaptation

```python
def detect_market_regime(df, lookback=50):
    """
    Identify current market conditions
    """
    # Calculate trend strength
    sma_20 = df['Close'].rolling(20).mean()
    sma_50 = df['Close'].rolling(50).mean()
    
    # Calculate volatility
    current_atr = atr_series(df, 14).iloc[-1]
    avg_atr = atr_series(df, 14).iloc[-lookback:].mean()
    
    # Determine regime
    if sma_20.iloc[-1] > sma_50.iloc[-1] * 1.02:
        trend = "STRONG_UPTREND"
    elif sma_20.iloc[-1] < sma_50.iloc[-1] * 0.98:
        trend = "STRONG_DOWNTREND"
    else:
        trend = "RANGING"
    
    if current_atr > avg_atr * 1.5:
        volatility = "HIGH"
    elif current_atr < avg_atr * 0.7:
        volatility = "LOW"
    else:
        volatility = "NORMAL"
    
    return {
        'trend': trend,
        'volatility': volatility,
        'recommendation': get_regime_params(trend, volatility)
    }

def get_regime_params(trend, volatility):
    """
    Adjust parameters based on market regime
    """
    if trend == "STRONG_UPTREND":
        return {
            'favor': 'LONG_SIGNALS',
            'allocation_step': 0.25,  # More aggressive on longs
            'filter_gap': 0.4  # More sensitive
        }
    
    elif trend == "STRONG_DOWNTREND":
        return {
            'favor': 'SHORT_SIGNALS',
            'allocation_step': 0.25,  # More aggressive on shorts
            'filter_gap': 0.4
        }
    
    else:  # RANGING
        return {
            'favor': 'NONE',
            'allocation_step': 0.15,  # Conservative
            'filter_gap': 0.6  # Strict filtering
        }
```

---

## Common Pitfalls

### 1. Over-Trading
```
❌ Problem: Taking every signal regardless of quality

Solution:
✅ Respect signal strength minimums (≥ 3)
✅ Wait for confluence between indicators
✅ Use strict filtering (ATR-based)
✅ Limit max concurrent positions (e.g., 5)
```

### 2. Ignoring Risk Management
```
❌ Problem: Inconsistent position sizing, no stop losses

Solution:
✅ Always use stop losses (no exceptions)
✅ Follow position sizing formula strictly
✅ Never risk more than 2% per trade
✅ Monitor portfolio-level risk
```

### 3. Chasing Trades
```
❌ Problem: Entering after signal candle closes far from zone

Solution:
✅ Enter only if price is still in zone
✅ Use limit orders at zone boundaries
✅ Skip if entry price gives poor RR ratio
✅ Wait for next signal patiently
```

### 4. Moving Stop Losses (Wrong Way)
```
❌ Problem: Moving stop loss further away to avoid getting stopped

Solution:
✅ Only move stop loss TOWARD profit (trailing)
✅ Never widen initial stop loss
✅ If trade goes against you, take the loss
✅ Accept that losses are part of trading
```

### 5. Emotional Trading
```
❌ Problem: Deviating from strategy after wins/losses

Solution:
✅ Follow the system mechanically
✅ Don't increase size after wins (revenge trading)
✅ Don't reduce size after losses (fear trading)
✅ Review performance weekly, not daily
```

### 6. Insufficient Backtesting
```
❌ Problem: Trading live without proper historical validation

Solution:
✅ Backtest on minimum 2 years of data
✅ Test across different market conditions
✅ Verify on out-of-sample data
✅ Paper trade for 1-3 months first
```

### 7. Ignoring Market Context
```
❌ Problem: Trading without considering broader market

Solution:
✅ Check overall market trend (index direction)
✅ Note major news events / earnings
✅ Reduce activity during extreme volatility
✅ Respect market holidays and gaps
```

---

## Quick Reference Card

### Trade Checklist

**Before Entry:**
- [ ] Signal strength ≥ 3
- [ ] Price inside FVG or OB zone
- [ ] Risk-reward ratio ≥ 1.5:1
- [ ] No conflicting signals
- [ ] Capital available
- [ ] Stop loss calculated
- [ ] Take profit levels set

**During Trade:**
- [ ] Monitor stop loss daily
- [ ] Update trailing stop when profitable
- [ ] Check for opposing signals
- [ ] Log any manual interventions
- [ ] Review position sizing

**After Exit:**
- [ ] Record trade outcome
- [ ] Calculate actual vs expected P&L
- [ ] Note what worked / didn't work
- [ ] Update performance metrics
- [ ] Identify improvement areas

### Performance Targets

| Metric | Target | Warning | Critical |
|--------|--------|---------|----------|
| Win Rate | 50-60% | < 45% | < 40% |
| Profit Factor | > 1.5 | < 1.3 | < 1.0 |
| Sharpe Ratio | > 1.0 | < 0.7 | < 0.5 |
| Max Drawdown | < 15% | 15-25% | > 25% |
| Avg RR Ratio | > 2:1 | < 1.5:1 | < 1:1 |

---

## Conclusion

TradePulse's trading strategy combines:
- **Technical rigor**: Multi-indicator confluence
- **Risk management**: Systematic position sizing and stops
- **Adaptability**: Signal strength classification
- **Discipline**: Rule-based execution

**Key Success Factors:**
1. Trust the system during drawdowns
2. Follow risk management without exception
3. Backtest thoroughly before live trading
4. Continuously monitor and optimize
5. Accept that no strategy wins 100% of the time

**Remember:**
> "The goal is not to predict the future, but to identify high-probability setups and manage risk effectively."

---

## Further Resources

- **Risk Management and Strategy rules.txt** - Detailed entry/exit rules
- **Backtest Reports** - Historical performance data in `resource/backtest_data/`
- **Test Files** - Unit tests demonstrating strategy components
- **Code Documentation** - Inline comments in strategy files

## Questions?

For implementation details, see the source code:
- `app/strategy/fvgorderblocks.py` - FVG strategy implementation
- `app/strategy/sonarlaplaceorderblocks.py` - Sonarlab implementation
- `app/agent/signal_generator.py` - Signal generation logic
- `app/agent/signal_strength.py` - Strength classification
- `app/agent/paper_trade_agent.py` - Trade execution engine

---

**Happy Trading! 📈✨**
