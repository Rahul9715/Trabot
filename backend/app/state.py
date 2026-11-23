from datetime import datetime, timezone, date
from zoneinfo import ZoneInfo
from .config import MAX_OPEN_POSITIONS, MAX_TRADES_PER_DAY, PAPER_TRADE_LIMITS_PATH
from .paper_limits import load_limits
from .config import PAPER_EXIT_SETTINGS_PATH
from .exit_settings import load_exit_settings

class RuntimeState:
    def __init__(self):
        limits = load_limits(PAPER_TRADE_LIMITS_PATH, {
            "max_open_positions": MAX_OPEN_POSITIONS,
            "max_trades_per_day": MAX_TRADES_PER_DAY,
        })
        self.max_open_positions = limits["max_open_positions"]
        self.max_trades_per_day = limits["max_trades_per_day"]
        self.max_risk_per_trade = limits["max_risk_per_trade"]
        exit_settings = load_exit_settings(PAPER_EXIT_SETTINGS_PATH)
        self.profit_exit_enabled = exit_settings["enabled"]
        self.profit_exit_target_percent = exit_settings["target_percent"]
        self.approval = None
        self.ticks = {}
        self.option_contracts = {}
        self.option_scan_status = "NOT_CONFIGURED"
        self.option_scan_error = None
        self.option_scan_last_at = None
        self.orders = []
        self.candidates = {}
        self.daily_realised_pnl = 0.0
        self.daily_date = datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat()
        self.connected = False
        self.feed_status = "NOT_CONFIGURED"
        self.feed_error = None
        self.last_feed_at = None
        self.global_feed_status = "NOT_CONFIGURED"
        self.global_feed_connected = False
        self.global_feed_error = None
        self.global_feed_last_update = None
        self.global_feed_symbols = []
        self.global_strategy_status = "NOT_CONFIGURED"
        self.global_strategy_last_scan = None
        self.global_strategy_last_action = "Configure Twelve Data and global paper symbols to enable this engine."
        self.global_strategy_error = None
        self.global_daily_realised_pnl_usd = 0.0
        self.global_daily_loss_baseline_usd = 0.0
        self.global_daily_date = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
        self.global_daily_loss_lock = False
        # The emergency stop starts released; the bot itself remains stopped.
        self.kill_switch = False
        self.bot_enabled = False
        self.bot_status = "STOPPED"
        self.autonomous_mode = False
        self.global_autonomous_mode = False
        self.operating_mode = "SEMI"
        self.execution_mode = "PAPER"
        self.autonomous_daily_loss_limit = None
        self.daily_loss_lock = False
        self.daily_loss_baseline = 0.0
        self.intelligence = None
        self.intelligence_sources = []
        self.intelligence_updated_at = None
        self.intelligence_status = "NOT_REFRESHED"
        self.intelligence_worker_status = "STOPPED"
        self.intelligence_worker_last_run = None
        self.intelligence_worker_error = None
        self.strategy_worker_status = "STOPPED"
        self.strategy_worker_last_scan = None
        self.strategy_worker_error = None
        self.strategy_last_signal = None
        self.strategy_last_action = "Waiting for configured NSE equity instruments."
        self.last_error = None

    def tick(self, symbol: str, data: dict):
        self.ticks[symbol] = data
        self.last_feed_at = datetime.now(timezone.utc).isoformat()

    def reset_daily_counters_if_needed(self):
        today = datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat()
        if today != self.daily_date:
            keep_autonomy = bool(self.autonomous_mode and self.bot_enabled and not self.kill_switch)
            keep_global_autonomy = bool(self.global_autonomous_mode and self.bot_enabled and not self.kill_switch)
            self.daily_date = today
            self.daily_realised_pnl = 0.0
            self.autonomous_mode = keep_autonomy
            self.global_autonomous_mode = keep_global_autonomy
            if not keep_autonomy:
                self.autonomous_daily_loss_limit = None
            self.daily_loss_lock = False
            self.daily_loss_baseline = 0.0
            self.approval = None
            # The emergency switch is independent of day counters. A daily
            # rollover must never release an engaged kill switch.
            self.operating_mode = "FULL" if keep_autonomy or keep_global_autonomy else "SEMI"

state = RuntimeState()

