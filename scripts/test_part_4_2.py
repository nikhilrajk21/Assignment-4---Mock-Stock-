"""Independent reference checks for the graded Part 4.2 behavior."""

from decimal import Decimal as D
from unittest import TestCase, main

from backend.backtest import BacktestRequest, run_backtest
from backend.indicators import SmaCandle, SmaRequest, calculate_sma
from backend.pnl import _apply_cost


def indicators(prices):
    candles = [SmaCandle(timestamp=f"2026-11-09T15:{i:02d}:00Z", close=price, complete=done)
               for i, (price, done) in enumerate(prices)]
    return SmaRequest(short_window=2, long_window=3, candles=candles)


class IndicatorTests(TestCase):
    def test_hand_calculated_reference_and_incremental_replay(self):
        prices = [(13, True), (10, True), (7, True), (13, True),
                  (19, True), (7, True), (1, True), (999, False)]
        # Each row is independent of the application: mean of the last two
        # closes, mean of the last three, then change of side across ties.
        expected = [(None, None, None), (11.5, None, None), (8.5, 10, None),
                    (10, 10, None), (16, 13, 'up'), (13, 13, None),
                    (4, 9, 'down'), (None, None, None)]
        batch = calculate_sma(indicators(prices))
        self.assertEqual([(p.short, p.long, p.crossover) for p in batch], expected)
        incremental = []
        for i in range(1, len(prices) + 1):
            incremental.append(calculate_sma(indicators(prices[:i]))[-1])
        self.assertEqual(batch, incremental)

    def test_forming_bar_never_enters_later_average(self):
        points = calculate_sma(indicators([(2, True), (999, False), (4, True), (6, True)]))
        self.assertEqual((points[1].short, points[1].long, points[1].crossover), (None, None, None))
        self.assertEqual((points[-1].short, points[-1].long), (5, 4))


class AccountingTests(TestCase):
    def test_weighted_basis_partial_sale_and_full_close(self):
        basis, realized = _apply_cost(None, D(0), 0, 'buy', 2, D(100))
        basis, realized = _apply_cost(basis, realized, 2, 'buy', 2, D(110))
        self.assertEqual((basis, realized), (D(105), D(0)))
        basis, realized = _apply_cost(basis, realized, 4, 'sell', 1, D(115))
        self.assertEqual((basis, realized), (D(105), D(10)))
        basis, realized = _apply_cost(basis, realized, 3, 'close', 3, D(100))
        self.assertEqual((basis, realized), (None, D(-5)))


class BacktestTests(TestCase):
    def test_next_bar_execution_and_terminal_unfilled_order(self):
        closes = [13, 10, 7, 13, 19, 7, 1, 2]
        candles = [{'timestamp': f'2026-11-09T15:{i:02d}:00Z', 'open': {5: 10, 7: 8}.get(i, close),
                    'close': close, 'complete': True} for i, close in enumerate(closes)]
        request = BacktestRequest(candles=candles, short_window=2, long_window=3, initial_cash=100, quantity=2)
        results = run_backtest(request)
        self.assertEqual([(o['side'], D(o['price'])) for o in results['orders']], [('buy', D(10)), ('sell', D(8))])
        self.assertEqual(D(results['equity_curve'][5]['unrealized']), D(-6))
        self.assertEqual(D(results['equity_curve'][-1]['realized']), D(-4))
        self.assertEqual(D(results['ending_equity']), D(96))
        shorter = request.model_copy(update={'candles': request.candles[:-1]})
        prefix = run_backtest(shorter)
        self.assertEqual(prefix['equity_curve'], results['equity_curve'][:-1])
        self.assertEqual(prefix['orders'][-1]['status'], 'unfilled')


if __name__ == '__main__':
    main()
