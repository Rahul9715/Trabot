from datetime import datetime, timezone, date
from zoneinfo import ZoneInfo

class RuntimeState:
    def __init__(self):
        self.approval = None
        self.ticks = {}
        self.orders = []
        self.candidates = {}
        self.daily_realised_pnl = 0.0
        self.daily_date = datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat()
        self.connected = False
        self.last_feed_at = None
        self.kill_switch = True
        self.bot_enabled = False
        self.bot_status = "STOPPED"
        self.autonomous_mode = False
        self.autonomous_daily_loss_limit = None
        self.daily_loss_lock = False
        self.daily_loss_baseline = 0.0
        self.intelligence = None
        self.intelligence_updated_at = None
        self.intelligence_status = "NOT_REFRESHED"
        self.last_error = None

    def tick(self, symbol: str, data: dict):
        self.ticks[symbol] = data
        self.last_feed_at = datetime.now(timezone.utc).isoformat()

    def reset_daily_counters_if_needed(self):
        today = datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat()
        if today != self.daily_date:
            self.daily_date = today
            self.daily_realised_pnl = 0.0
            self.autonomous_mode = False
            self.autonomous_daily_loss_limit = None
            self.daily_loss_lock = False
            self.daily_loss_baseline = 0.0
            self.approval = None
            self.kill_switch = True

state = RuntimeState()
