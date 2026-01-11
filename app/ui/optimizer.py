"""
Optimizer - Run backtests with different parameter combinations to find optimal settings.
"""
import logging
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import List, Dict, Any, Tuple, Optional
from itertools import product
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class BacktestOptimizer:
    """Optimize backtest parameters to maximize profit."""
    
    def __init__(
        self,
        data_dict: Dict[str, pd.DataFrame],
        strategy_class,
        trade_agent_class,
        signal_generator
    ):
        """
        Initialize optimizer.
        
        Args:
            data_dict: Dictionary mapping symbol to DataFrame
            strategy_class: Strategy class to use
            trade_agent_class: TradeAgent class to use
            signal_generator: SignalGenerator instance
        """
        self.data_dict = data_dict
        self.strategy_class = strategy_class
        self.trade_agent_class = trade_agent_class
        self.signal_generator = signal_generator
        self.results = []
    
    def optimize(
        self,
        param_ranges: Dict[str, List[Any]],
        metric: str = 'total_pnl',
        max_workers: int = 4
    ) -> pd.DataFrame:
        """
        Run optimization over parameter ranges.
        
        Args:
            param_ranges: Dictionary of parameter names to lists of values to test
                Example: {
                    'risk_reward_ratio': [1.5, 2.0, 2.5, 3.0],
                    'stop_loss_pct': [0.02, 0.03, 0.04, 0.05],
                    'allocation_step': [0.15, 0.2, 0.25]
                }
            metric: Metric to optimize ('total_pnl', 'win_rate', 'sharpe_ratio', etc.)
            max_workers: Number of parallel workers
        
        Returns:
            DataFrame with results sorted by metric
        """
        logger.info("Starting optimization...")
        
        # Generate all parameter combinations
        param_names = list(param_ranges.keys())
        param_values = list(param_ranges.values())
        combinations = list(product(*param_values))
        
        logger.info(f"Testing {len(combinations)} parameter combinations")
        
        # Run backtests for each combination
        results = []
        
        if max_workers > 1:
            # Parallel execution
            with ProcessPoolExecutor(max_workers=max_workers) as executor:
                futures = {}
                for combo in combinations:
                    params = dict(zip(param_names, combo))
                    future = executor.submit(self._run_single_backtest, params)
                    futures[future] = params
                
                for i, future in enumerate(as_completed(futures)):
                    params = futures[future]
                    try:
                        result = future.result()
                        results.append(result)
                        logger.info(f"[{i+1}/{len(combinations)}] Completed: {params}")
                    except Exception as e:
                        logger.error(f"Error with params {params}: {e}")
        else:
            # Sequential execution
            for i, combo in enumerate(combinations):
                params = dict(zip(param_names, combo))
                try:
                    result = self._run_single_backtest(params)
                    results.append(result)
                    logger.info(f"[{i+1}/{len(combinations)}] Completed: {params}")
                except Exception as e:
                    logger.error(f"Error with params {params}: {e}")
        
        # Convert to DataFrame
        results_df = pd.DataFrame(results)
        
        # Sort by metric (descending for profit metrics, ascending for drawdown)
        ascending = metric in ['max_drawdown', 'max_drawdown_pct']
        results_df = results_df.sort_values(by=metric, ascending=ascending)
        
        self.results = results_df
        logger.info(f"Optimization complete. Best {metric}: {results_df.iloc[0][metric]:.2f}")
        
        return results_df
    
    def _run_single_backtest(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run a single backtest with given parameters.
        
        Args:
            params: Dictionary of parameters for TradeAgent
        
        Returns:
            Dictionary with backtest results and metrics
        """
        try:
            # Create trade agent with specified parameters
            agent_params = {
                'initial_capital': params.get('initial_capital', 100000.0),
                'target_pct': params.get('target_pct', 0.07),
                'stop_loss_pct': params.get('stop_loss_pct', 0.03),
                'allocation_step': params.get('allocation_step', 0.2)
            }
            
            # Add risk_reward_ratio if specified
            if 'risk_reward_ratio' in params:
                agent_params['risk_reward_ratio'] = params['risk_reward_ratio']
            
            trade_agent = self.trade_agent_class(**agent_params)
            
            # Generate signals for all symbols
            all_signals = []
            for symbol, df in self.data_dict.items():
                signals = self.signal_generator.generate_signals(df, symbol)
                all_signals.extend(signals)
            
            # Sort signals by date
            all_signals = sorted(
                all_signals,
                key=lambda s: s.date if s.date is not None else pd.Timestamp.min
            )
            
            # Execute trades (use first DataFrame as reference)
            first_df = list(self.data_dict.values())[0]
            trades_df = trade_agent.execute_signals(first_df, all_signals)
            
            # Calculate metrics
            metrics = self._calculate_metrics(trade_agent, trades_df)
            
            # Add parameters to results
            result = {**params, **metrics}
            
            return result
            
        except Exception as e:
            logger.error(f"Error running backtest: {e}")
            # Return params with zero metrics on error
            return {
                **params,
                'total_pnl': 0,
                'total_return_pct': 0,
                'win_rate': 0,
                'profit_factor': 0,
                'max_drawdown': 0,
                'sharpe_ratio': 0,
                'total_trades': 0,
                'error': str(e)
            }
    
    def _calculate_metrics(self, trade_agent, trades_df: pd.DataFrame) -> Dict[str, float]:
        """
        Calculate performance metrics from backtest results.
        
        Args:
            trade_agent: TradeAgent instance
            trades_df: DataFrame of executed trades
        
        Returns:
            Dictionary of metrics
        """
        metrics = {}
        
        # Basic metrics
        metrics['total_pnl'] = trade_agent.final_pnl
        metrics['final_balance'] = trade_agent.final_balance
        metrics['total_return_pct'] = (
            (trade_agent.final_balance - trade_agent.initial_capital) / 
            trade_agent.initial_capital * 100
        )
        
        # Trade statistics
        metrics['total_trades'] = len(trades_df)
        
        if len(trades_df) > 0:
            # Detect PnL column name (could be 'PnL' or 'pnl')
            pnl_col = 'pnl' if 'pnl' in trades_df.columns else 'PnL'
            cash_after_col = 'cash_after' if 'cash_after' in trades_df.columns else 'Cash_After'
            
            # Win/Loss metrics
            if pnl_col in trades_df.columns:
                completed_trades = trades_df[trades_df[pnl_col] != 0]
            else:
                completed_trades = trades_df
            
            if len(completed_trades) > 0 and pnl_col in trades_df.columns:
                winning_trades = completed_trades[completed_trades[pnl_col] > 0]
                losing_trades = completed_trades[completed_trades[pnl_col] < 0]
                
                metrics['winning_trades'] = len(winning_trades)
                metrics['losing_trades'] = len(losing_trades)
                metrics['win_rate'] = (
                    len(winning_trades) / len(completed_trades) * 100
                    if len(completed_trades) > 0 else 0
                )
                
                # Profit factor
                total_wins = winning_trades[pnl_col].sum() if len(winning_trades) > 0 else 0
                total_losses = abs(losing_trades[pnl_col].sum()) if len(losing_trades) > 0 else 0
                metrics['profit_factor'] = (
                    total_wins / total_losses if total_losses > 0 else float('inf')
                )
                
                # Average trade metrics
                metrics['avg_win'] = (
                    winning_trades[pnl_col].mean() if len(winning_trades) > 0 else 0
                )
                metrics['avg_loss'] = (
                    losing_trades[pnl_col].mean() if len(losing_trades) > 0 else 0
                )
                metrics['avg_trade'] = completed_trades[pnl_col].mean()
                
                # Expectancy
                if metrics['win_rate'] > 0:
                    win_rate_decimal = metrics['win_rate'] / 100
                    metrics['expectancy'] = (
                        win_rate_decimal * metrics['avg_win'] - 
                        (1 - win_rate_decimal) * abs(metrics['avg_loss'])
                    )
                else:
                    metrics['expectancy'] = 0
                
                # Maximum consecutive wins/losses
                metrics['max_consecutive_wins'] = trade_agent.max_winning_streak
                metrics['max_consecutive_losses'] = trade_agent.max_losing_streak
                
                # Calculate drawdown
                if cash_after_col in trades_df.columns:
                    equity_curve = trades_df[cash_after_col].values
                    drawdown = self._calculate_drawdown(equity_curve)
                    metrics['max_drawdown'] = drawdown['max_drawdown']
                    metrics['max_drawdown_pct'] = drawdown['max_drawdown_pct']
                else:
                    metrics['max_drawdown'] = 0
                    metrics['max_drawdown_pct'] = 0
                
                # Sharpe ratio (simplified - assuming daily returns)
                if pnl_col in trades_df.columns and len(trades_df) > 1:
                    returns = trades_df[pnl_col].values
                    if len(returns) > 0 and returns.std() > 0:
                        metrics['sharpe_ratio'] = (
                            returns.mean() / returns.std() * np.sqrt(252)
                        )
                    else:
                        metrics['sharpe_ratio'] = 0
                else:
                    metrics['sharpe_ratio'] = 0
            else:
                # No completed trades
                metrics['winning_trades'] = 0
                metrics['losing_trades'] = 0
                metrics['win_rate'] = 0
                metrics['profit_factor'] = 0
                metrics['avg_win'] = 0
                metrics['avg_loss'] = 0
                metrics['avg_trade'] = 0
                metrics['expectancy'] = 0
                metrics['max_consecutive_wins'] = 0
                metrics['max_consecutive_losses'] = 0
                metrics['max_drawdown'] = 0
                metrics['max_drawdown_pct'] = 0
                metrics['sharpe_ratio'] = 0
        else:
            # No trades
            for key in ['winning_trades', 'losing_trades', 'win_rate', 'profit_factor',
                       'avg_win', 'avg_loss', 'avg_trade', 'expectancy',
                       'max_consecutive_wins', 'max_consecutive_losses',
                       'max_drawdown', 'max_drawdown_pct', 'sharpe_ratio']:
                metrics[key] = 0
        
        return metrics
    
    def _calculate_drawdown(self, equity_curve: np.ndarray) -> Dict[str, float]:
        """
        Calculate maximum drawdown from equity curve.
        
        Args:
            equity_curve: Array of portfolio values over time
        
        Returns:
            Dictionary with max_drawdown and max_drawdown_pct
        """
        if len(equity_curve) == 0:
            return {'max_drawdown': 0, 'max_drawdown_pct': 0}
        
        # Calculate running maximum
        running_max = np.maximum.accumulate(equity_curve)
        
        # Calculate drawdown
        drawdown = running_max - equity_curve
        max_drawdown = np.max(drawdown)
        
        # Calculate percentage drawdown
        max_drawdown_pct = (max_drawdown / running_max[np.argmax(drawdown)] * 100
                           if running_max[np.argmax(drawdown)] > 0 else 0)
        
        return {
            'max_drawdown': max_drawdown,
            'max_drawdown_pct': max_drawdown_pct
        }
    
    def get_best_params(self, metric: str = 'total_pnl') -> Dict[str, Any]:
        """
        Get the best parameter combination.
        
        Args:
            metric: Metric to optimize
        
        Returns:
            Dictionary of best parameters
        """
        if self.results is None or len(self.results) == 0:
            return {}
        
        ascending = metric in ['max_drawdown', 'max_drawdown_pct']
        best = self.results.sort_values(by=metric, ascending=ascending).iloc[0]
        
        return best.to_dict()
    
    def plot_results(self, param_name: str, metric: str = 'total_pnl'):
        """
        Plot optimization results for a single parameter.
        
        Args:
            param_name: Parameter name to plot
            metric: Metric to plot on y-axis
        """
        try:
            import matplotlib.pyplot as plt
            
            if self.results is None or len(self.results) == 0:
                logger.warning("No results to plot")
                return
            
            df = self.results.copy()
            
            # Group by parameter if there are multiple combinations
            if param_name in df.columns:
                grouped = df.groupby(param_name)[metric].mean().sort_index()
                
                plt.figure(figsize=(10, 6))
                plt.plot(grouped.index, grouped.values, marker='o')
                plt.xlabel(param_name)
                plt.ylabel(metric)
                plt.title(f'{metric} vs {param_name}')
                plt.grid(True, alpha=0.3)
                plt.tight_layout()
                plt.show()
            else:
                logger.warning(f"Parameter '{param_name}' not found in results")
                
        except ImportError:
            logger.warning("matplotlib not available for plotting")
        except Exception as e:
            logger.error(f"Error plotting results: {e}")
