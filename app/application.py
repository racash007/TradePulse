import tkinter as tk
from tkinter import ttk, messagebox
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
import matplotlib.axes as maxes
from pandas import DataFrame
import os
import pandas as pd

# Try package imports first (when running as part of package), fall back to local-relative imports
try:
    from app.strategy.fvgorderblocks import FVGOrderBlocks
    from app.strategy.sonarlaborderblocks import SonarlabOrderBlocks
    from app.utility.utility import load_data
    from app.strategy.signal_generator import SignalGenerator
    from app.strategy.trade_agent import TradeAgent
except Exception:
    # running as a script (python app/application.py) - import from local module names
    from strategy.fvgorderblocks import FVGOrderBlocks
    from strategy.sonarlaborderblocks import SonarlabOrderBlocks
    from utility.utility import load_data
    from strategy.signal_generator import SignalGenerator
    from strategy.trade_agent import TradeAgent

# Fix data_dir: assume repository root is parent of this app/ folder
data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'resource', 'data')
if not os.path.isdir(data_dir):
    # try alternative path if the file layout differs
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'resource', 'data')

CSV_FILES = [f for f in os.listdir(data_dir) if f.endswith('.csv')] if os.path.isdir(data_dir) else []


def plot_both_strategies_on_ax(ax: maxes.Axes, df: DataFrame, file_name: str):
    """
    Run both strategies and plot them onto the provided Axes.
    Returns tuple (fvg_strategy_instance, sonar_strategy_instance).
    """
    fvg = FVGOrderBlocks()
    fvg.run(df)
    sonar = SonarlabOrderBlocks()
    sonar.run(df)

    # Draw candles once (we'll let the first strategy draw candles as they both draw candles the same way)
    # Call plotting with ax for both; they add boxes/pieces on the same axes.
    fvg.plot(df, title=f"Combined Order Blocks [{file_name}]", ax=ax)
    # let sonar use its default title (omit explicit None)
    sonar.plot(df, ax=ax)
    return fvg, sonar


def plot_single_strategy_on_ax(ax: maxes.Axes, df: DataFrame, file_name: str, strategy: str):
    if strategy == "FVGOrderBlocks":
        strat = FVGOrderBlocks()
        strat.run(df)
        strat.plot(df, title=f"FVG Order Blocks [{file_name}]", ax=ax)
    else:
        strat = SonarlabOrderBlocks()
        strat.run(df)
        strat.plot(df, title=f"Sonarlab Order Blocks [{file_name}]", ax=ax)
    return strat


class TradePulseApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("TradePulse Order Blocks Viewer")
        self.geometry("1200x800")
        self.selected_file = tk.StringVar(value=CSV_FILES[0] if CSV_FILES else "")
        # strategy selection removed; SignalGenerator will always run both strategies
        self.canvas = None
        self.figure = None
        # Create main canvas and scrollbar
        self.main_canvas = tk.Canvas(self, borderwidth=0, background="#f0f0f0")
        self.v_scrollbar = tk.Scrollbar(self, orient="vertical", command=self.main_canvas.yview)
        self.main_canvas.configure(yscrollcommand=self.v_scrollbar.set)
        self.v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.main_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        # Create scrollable frame inside canvas
        self.scrollable_frame = tk.Frame(self.main_canvas, background="#f0f0f0")
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.main_canvas.configure(scrollregion=self.main_canvas.bbox("all"))
        )
        self.main_canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        # UI containers
        self.signals_frame = None
        self.signals_table = None
        self.plot_frame = None
        self.create_widgets()

    def create_widgets(self):
        self.create_file_dropdown()
        self.create_plot_button()
        self.create_plot_frame()
        self.create_signals_frame()

    def create_file_dropdown(self):
        file_label = tk.Label(self.scrollable_frame, text="Select CSV file:")
        file_label.pack(pady=5)
        file_dropdown = ttk.Combobox(self.scrollable_frame, textvariable=self.selected_file, values=CSV_FILES, state="readonly", width=80)
        file_dropdown.pack(pady=5)

    def create_plot_button(self):
        plot_btn = tk.Button(self.scrollable_frame, text="Plot Graph", command=self.plot_graph)
        plot_btn.pack(pady=10)

    def create_plot_frame(self):
        self.plot_frame = tk.Frame(self.scrollable_frame)
        self.plot_frame.pack(fill=tk.BOTH, expand=True)

    def create_signals_frame(self):
        self.signals_frame = tk.Frame(self.scrollable_frame)
        self.signals_frame.pack(fill=tk.X, pady=10)
        self.signals_table = None
        # summary frame for trade agent metrics below the signals table
        self.summary_frame = tk.Frame(self.scrollable_frame)
        self.summary_frame.pack(fill=tk.X, pady=10)
        # trades frame to list executed trades below the summary
        self.trades_frame = tk.Frame(self.scrollable_frame)
        self.trades_frame.pack(fill=tk.BOTH, pady=5)

    def plot_graph(self):
        file_name = self.selected_file.get()
        if not file_name:
            messagebox.showerror("Error", "No file selected.")
            return
        try:
            filter_text = file_name.split("-")[4].replace(".csv", "") if "-" in file_name else file_name.replace(".csv", "")
            df = load_data(filter_text)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load data: {e}")
            return
        self.destroy_widget()
        self.figure = plt.Figure(figsize=(14, 8))
        ax = self.figure.add_subplot(111)
        # Always plot both strategies (SignalGenerator will analyze both)
        fvg_strat, sonar_strat = plot_both_strategies_on_ax(ax, df, file_name)
        signals = []
        try:
            signals.extend(fvg_strat.get_signals() or [])
        except Exception:
            pass
        try:
            signals.extend(sonar_strat.get_signals() or [])
        except Exception:
            pass
        # Embed plot in Tkinter
        self.canvas = FigureCanvasTkAgg(self.figure, master=self.plot_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        # Show signals in table (date, price, shares, type, signalStrength)
        columns = ("date", "price", "shares", "type", "signalStrength")
        self.signals_table = ttk.Treeview(self.signals_frame, columns=columns, show="headings", height=8)
        for col in columns:
            self.signals_table.heading(col, text=col.capitalize())
            self.signals_table.column(col, width=120)
        # If Both selected, prefer enhanced signals from SignalGenerator (richer schema)
        enhanced_list = []
        try:
            sg = SignalGenerator()
            enhanced_list = sg.generate_from_file(df)
        except Exception:
            enhanced_list = []

        filtered_list = [e for e in enhanced_list if getattr(e, 'signalStrength', 0) != 0]

        if not filtered_list:
            messagebox.showinfo("No Signals", "No signals with non-zero strength found for the selected file.")
        else:
            # build dataframe for display
            df_display = sg.to_dataframe(filtered_list)
            # create a temporary TradeAgent to compute projected shares based on initial capital
            ta_for_calc = TradeAgent()
            for _, r in df_display.iterrows():
                dt = r.get('date')
                if dt is not None:
                    try:
                        dt_str = pd.to_datetime(dt).strftime('%Y-%m-%d')
                    except Exception:
                        dt_str = str(dt)
                else:
                    dt_str = None
                # compute projected number of shares using allocation_pct * initial capital
                price = r.get('price')
                try:
                    pct = ta_for_calc.allocation_pct(int(r.get('signalStrength') or 0))
                    shares = int((ta_for_calc.initial_capital * pct) // float(price)) if price and pct > 0 else 0
                except Exception:
                    shares = 0
                values = [dt_str, r.get('price'), shares, r.get('type'), r.get('signalStrength')]
                self.signals_table.insert("", "end", values=values)
        # Add vertical scrollbar to signals table
        v_scrollbar = ttk.Scrollbar(self.signals_frame, orient="vertical", command=self.signals_table.yview)
        self.signals_table.configure(yscrollcommand=v_scrollbar.set)
        # Add horizontal scrollbar to signals table
        h_scrollbar = ttk.Scrollbar(self.signals_frame, orient="horizontal", command=self.signals_table.xview)
        self.signals_table.configure(xscrollcommand=h_scrollbar.set)
        self.signals_table.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10)
        v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        # Execute signals through TradeAgent and show summary (pass market df and enhanced signal objects)
        try:
            ta = TradeAgent()
            trades_df = ta.execute_signals(df, filtered_list)
            summary = ta.get_summary()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to execute signals: {e}")
            summary = None

        if summary is not None:
            # Clear previous summary widgets
            for w in self.summary_frame.winfo_children():
                w.destroy()
            # Create a compact treeview to show the summary below the signals table
            summary_tree = ttk.Treeview(self.summary_frame, columns=("metric", "value"), show="headings", height=8)
            summary_tree.heading("metric", text="Metric")
            summary_tree.heading("value", text="Value")
            summary_tree.column("metric", width=200)
            summary_tree.column("value", width=200)
            summary_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
            for metric, value in summary.items():
                summary_tree.insert("", "end", values=(metric, value))
            # Populate trades table below summary
            for w in self.trades_frame.winfo_children():
                w.destroy()
            if trades_df is not None and not trades_df.empty:
                cols = ("entry_date", "exit_date", "side", "entry_price", "exit_price", "shares", "pnl", "signalStrength")
                trades_tree = ttk.Treeview(self.trades_frame, columns=cols, show='headings', height=8)
                for c in cols:
                    trades_tree.heading(c, text=c.replace('_', ' ').title())
                    trades_tree.column(c, width=120)
                # insert rows
                for _, t in trades_df.iterrows():
                    entry_date = t.get('entry_date')
                    ed = None
                    if entry_date is not None:
                        try:
                            ed = pd.to_datetime(entry_date).strftime('%Y-%m-%d')
                        except Exception:
                            ed = str(entry_date)
                    exit_date = t.get('exit_date')
                    exd = None
                    if exit_date is not None:
                        try:
                            exd = pd.to_datetime(exit_date).strftime('%Y-%m-%d')
                        except Exception:
                            exd = str(exit_date)
                    row = [ed, exd, t.get('side'), t.get('entry_price'), t.get('exit_price'), t.get('shares'), t.get('pnl'), t.get('signalStrength')]
                    trades_tree.insert('', 'end', values=row)
                trades_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

    def destroy_widget(self):
        # Clear previous plot
        for widget in self.plot_frame.winfo_children():
            widget.destroy()
        for widget in self.signals_frame.winfo_children():
            widget.destroy()
        # Clear summary frame
        for widget in self.summary_frame.winfo_children():
            widget.destroy()
        # Clear trades frame
        for widget in self.trades_frame.winfo_children():
            widget.destroy()


if __name__ == "__main__":
    app = TradePulseApp()
    app.mainloop()
