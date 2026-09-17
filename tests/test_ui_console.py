import io
import unittest
from contextlib import redirect_stdout

from tools.ui import UI


class ConsoleUiTests(unittest.TestCase):
    def test_shadow_win_rate_is_na_without_closed_trades(self):
        ui = UI()
        ui.update(
            balance=1000.0,
            db_stats={"total_shadow_trades": 0, "shadow_win_rate": 50.0},
            scanner=[],
            trades=[],
            recent_closed_trades=[],
        )
        ui._render_count = 9

        output = io.StringIO()
        with redirect_stdout(output):
            ui.render()

        self.assertIn("SHADOW WR: N/A", output.getvalue())

    def test_shadow_win_rate_is_shown_with_closed_trades(self):
        ui = UI()
        ui.update(
            balance=1000.0,
            db_stats={"total_shadow_trades": 4, "shadow_win_rate": 25.0},
            scanner=[],
            trades=[],
            recent_closed_trades=[],
        )
        ui._render_count = 9

        output = io.StringIO()
        with redirect_stdout(output):
            ui.render()

        self.assertIn("SHADOW WR: 25.0%", output.getvalue())


if __name__ == "__main__":
    unittest.main()
