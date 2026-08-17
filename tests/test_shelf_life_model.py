from __future__ import annotations

import unittest

from src.core_predictor import predict_shelf_life


class ShelfLifeModelTests(unittest.TestCase):
    @staticmethod
    def predict_days(temperature_c: float, hardness: float) -> float:
        return predict_shelf_life(
            temperature_c,
            hardness,
        ).estimated_shelf_life_days

    def test_hardness_60_temperature_curve_has_no_abrupt_middle_drop(self) -> None:
        temperatures = (0, 5, 10, 15, 20, 25)
        results = [self.predict_days(temperature, 60) for temperature in temperatures]

        self.assertEqual(results, [25.6, 17.3, 11.4, 6.9, 3.8, 2.0])
        self.assertTrue(all(left > right for left, right in zip(results, results[1:])))

        interval_drops = [left - right for left, right in zip(results, results[1:])]
        self.assertTrue(
            all(left >= right for left, right in zip(interval_drops, interval_drops[1:]))
        )

    def test_dense_grid_is_monotonic_in_temperature_and_hardness(self) -> None:
        temperatures = [index / 2 for index in range(51)]
        hardness_values = [60 + index / 2 for index in range(61)]

        for hardness in hardness_values:
            results = [self.predict_days(temperature, hardness) for temperature in temperatures]
            self.assertTrue(
                all(left >= right for left, right in zip(results, results[1:])),
                f"temperature curve increased at hardness {hardness}: {results}",
            )

        for temperature in temperatures:
            results = [self.predict_days(temperature, hardness) for hardness in hardness_values]
            self.assertTrue(
                all(left <= right for left, right in zip(results, results[1:])),
                f"hardness curve decreased at temperature {temperature}: {results}",
            )

    def test_original_measured_anchors_are_preserved(self) -> None:
        self.assertEqual(self.predict_days(0, 70), 37.0)
        self.assertEqual(self.predict_days(5, 70), 25.0)
        self.assertEqual(self.predict_days(25, 60), 2.0)


if __name__ == "__main__":
    unittest.main()
