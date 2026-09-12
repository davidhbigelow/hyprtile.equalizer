#!/usr/bin/python3

import importlib.machinery
import importlib.util
import os
import pathlib
import sys
import unittest

_scripts = str(pathlib.Path(__file__).parents[1] / "scripts")
sys.path.insert(0, _scripts)
_loader = importlib.machinery.SourceFileLoader(
    "equalize_watch", os.path.join(_scripts, "equalize-watch")
)
_spec = importlib.util.spec_from_loader("equalize_watch", _loader)
w = importlib.util.module_from_spec(_spec)
_loader.exec_module(w)


def grid():
    rects = {}
    cells = {}
    for row in range(3):
        for col in range(3):
            index = row * 3 + col
            addr = f"0x{index + 1:x}"
            rects[addr] = (col * 318, row * 318, 300, 300)
            cells[addr] = index
    return rects, cells


class EqualizeLayoutTests(unittest.TestCase):

    def test_width_resize_only_changes_selected_row(self):
        rects, cells = grid()
        resized = w.resize_slot_layout(rects, cells, "0x5", (500, 300))

        self.assertEqual(resized["0x5"], (218, 318, 500, 300))
        self.assertEqual(resized["0x4"], (0, 318, 200, 300))
        self.assertEqual(resized["0x6"], (736, 318, 200, 300))
        for addr in ("0x1", "0x2", "0x3", "0x7", "0x8", "0x9"):
            self.assertEqual(resized[addr], rects[addr])

    def test_height_resize_changes_complete_row_bands(self):
        rects, cells = grid()
        resized = w.resize_slot_layout(rects, cells, "0x5", (300, 500))

        for addr in ("0x1", "0x2", "0x3"):
            self.assertEqual(resized[addr][1:], (0, resized[addr][2], 200))
        for addr in ("0x4", "0x5", "0x6"):
            self.assertEqual((resized[addr][1], resized[addr][3]), (218, 500))
        for addr in ("0x7", "0x8", "0x9"):
            self.assertEqual((resized[addr][1], resized[addr][3]), (736, 200))

    def test_corner_resize_matches_extreme_example(self):
        rects, cells = grid()
        resized = w.resize_slot_layout(rects, cells, "0x5", (500, 500))

        self.assertEqual(resized["0x5"], (218, 218, 500, 500))
        self.assertEqual(resized["0x1"], (0, 0, 300, 200))
        self.assertEqual(resized["0x4"], (0, 218, 200, 500))
        self.assertEqual(resized["0x9"], (636, 736, 300, 200))

    def test_repeated_resize_uses_current_custom_geometry(self):
        rects, cells = grid()
        first = w.resize_slot_layout(rects, cells, "0x5", (500, 300))
        second = w.resize_slot_layout(first, cells, "0x5", (600, 300))

        self.assertEqual(second["0x4"][2], 150)
        self.assertEqual(second["0x5"], (168, 318, 600, 300))
        self.assertEqual(second["0x6"][2], 150)

    def test_growth_clamps_at_neighbor_minimum(self):
        rects, cells = grid()
        resized = w.resize_slot_layout(rects, cells, "0x5", (1000, 300))

        self.assertEqual(resized["0x4"][2], w.MIN_TILE_SIZE)
        self.assertEqual(resized["0x5"][2], 740)
        self.assertEqual(resized["0x6"][2], w.MIN_TILE_SIZE)

    def test_dragged_window_inherits_destination_slot(self):
        rects, cells = grid()
        custom = w.resize_slot_layout(rects, cells, "0x5", (500, 500))
        swapped, new_cells = w.swap_slot_layout(custom, cells, "0x1", (468, 468))

        self.assertEqual(swapped["0x1"], custom["0x5"])
        self.assertEqual(swapped["0x5"], custom["0x1"])
        self.assertEqual(new_cells["0x1"], cells["0x5"])
        self.assertEqual(new_cells["0x5"], cells["0x1"])

    def test_drop_in_own_slot_does_not_swap(self):
        rects, cells = grid()
        swapped, new_cells = w.swap_slot_layout(rects, cells, "0x5", (468, 468))

        self.assertEqual(swapped, rects)
        self.assertEqual(new_cells, cells)

    def test_keyboard_right_uses_next_occupied_slot_in_stretched_row(self):
        rects, cells = grid()
        rects.pop("0x9")
        cells.pop("0x9")
        rects["0x8"] = (318, 636, 618, 300)

        swapped, new_cells = w.swap_directional_layout(
            rects, cells, "0x7", (627, 786)
        )

        self.assertEqual(swapped["0x7"], rects["0x8"])
        self.assertEqual(swapped["0x8"], rects["0x7"])
        self.assertEqual(new_cells["0x7"], 7)
        self.assertEqual(new_cells["0x8"], 6)

    def test_keyboard_right_at_last_occupied_slot_stays_put(self):
        rects, cells = grid()
        rects.pop("0x9")
        cells.pop("0x9")
        rects["0x8"] = (318, 636, 618, 300)

        swapped, new_cells = w.swap_directional_layout(
            rects, cells, "0x8", (1000, 786)
        )

        self.assertEqual(swapped, rects)
        self.assertEqual(new_cells, cells)

    def test_swap_constraints_expand_destination_before_move(self):
        rects = {
            "0x1": (0, 0, 400, 300),
            "0x2": (418, 0, 200, 300),
            "0x3": (636, 0, 300, 300),
        }
        cells = {"0x1": 0, "0x2": 1, "0x3": 2}
        swapped, new_cells = w._swap_slots(rects, cells, "0x1", "0x2")

        fitted = w.fit_slot_constraints(swapped, new_cells, {"0x1": (350, 300)})

        self.assertEqual(fitted["0x1"][2], 350)
        self.assertEqual(fitted["0x1"][0], 268)
        self.assertEqual(fitted["0x2"][2], 250)

    def test_constraint_fit_does_not_shrink_other_cached_minima(self):
        rects, cells = grid()
        constraints = {
            "0x4": (250, 80),
            "0x5": (500, 80),
            "0x6": (250, 80),
        }

        fitted = w.fit_slot_constraints(rects, cells, constraints)

        self.assertGreaterEqual(fitted["0x4"][2], 250)
        self.assertGreaterEqual(fitted["0x5"][2], 400)
        self.assertGreaterEqual(fitted["0x6"][2], 250)

    def _stub_rows(self, n, ws_size):
        original_rows = w.current_rows
        original_geometry = w.geometry
        original_dispatch = w.dispatch

        def rows(_mon, _ws):
            return [
                {
                    "address": "0x%x" % (i + 1),
                    "at": [0, 0],
                    "size": [1, 1],
                    "workspace": {"id": 1},
                }
                for i in range(n)
            ]

        w.current_rows = rows
        w.geometry = lambda _mon: {"l": 0, "t": 0, "w": ws_size[0], "h": ws_size[1]}
        w.dispatch = lambda _command: None
        self.addCleanup(setattr, w, "current_rows", original_rows)
        self.addCleanup(setattr, w, "geometry", original_geometry)
        self.addCleanup(setattr, w, "dispatch", original_dispatch)

    def _grid_rects(self, n):
        cells = w.cell_list(None, 1)
        rects = {
            "0x%x" % (i + 1): (x, y, width, height)
            for i, (_cx, _cy, x, y, width, height) in enumerate(cells)
        }
        cell_map = {"0x%x" % (i + 1): i for i in range(len(cells))}
        return rects, cell_map

    def test_fill_off_restores_custom_pre_stretch_rectangle(self):
        original_cells = w.cell_list
        original_geometry = w.geometry
        original_dispatch = w.dispatch
        w.cell_list = lambda _mon, _ws: [
            (50, 50, 0, 0, 100, 100),
            (168, 50, 118, 0, 100, 100),
        ]
        w.geometry = lambda _mon: {"l": 0, "t": 0, "w": 400, "h": 200}
        w.dispatch = lambda _command: None
        self.addCleanup(setattr, w, "cell_list", original_cells)
        self.addCleanup(setattr, w, "geometry", original_geometry)
        self.addCleanup(setattr, w, "dispatch", original_dispatch)
        custom = (150, 20, 120, 140)

        restored, state = w.apply_fill_in_place(
            None,
            1,
            "off",
            {"0x1": (0, 0, 100, 100), "0x2": (150, 20, 250, 140)},
            {"0x1": 0, "0x2": 1},
            ("horizontal", {"0x2": custom}),
        )

        self.assertEqual(restored["0x2"], custom)
        self.assertEqual(state, (None, None))

    def test_stretch_plan_adds_gap_tile_only_when_needed(self):
        self.assertEqual(w.stretch_plan("vertical", 7), [("down", 5), ("gap", 6)])
        self.assertEqual(w.stretch_plan("vertical", 8), [("down", 5)])
        self.assertEqual(w.stretch_plan("vertical", 10), [("down", 7), ("gap", 9)])
        self.assertEqual(w.stretch_plan("vertical", 11), [("down", 7)])
        self.assertEqual(w.stretch_plan("vertical", 13), [("down", 11), ("gap", 12)])
        self.assertEqual(w.stretch_plan("horizontal", 7), [("row", 6)])
        self.assertEqual(w.stretch_plan("off", 7), [])
        self.assertEqual(w.stretch_plan("vertical", 9), [])
        self.assertEqual(w.stretch_plan("vertical", 2), [])

    def test_extend_last_cell_closes_bottom_row_gap(self):
        self._stub_rows(7, (1000, 600))
        rects, cell_map = self._grid_rects(7)
        targets = [(addr, *rect) for addr, rect in rects.items()]
        filled = w.extend_last_cell(None, targets, cell_map, "vertical")
        filled_map = {addr: (x, y, w, h) for addr, x, y, w, h in filled}

        pad = w.GAPS_OUT + w.BORDER
        bottom = int(round(w.geometry(None)["t"] + pad + w.geometry(None)["h"] - 2 * pad))
        self.assertEqual(filled_map["0x6"][1] + filled_map["0x6"][3], bottom)
        self.assertEqual(
            filled_map["0x7"][0] + filled_map["0x7"][2],
            filled_map["0x6"][0] - w.GRID_GAP,
        )
        for addr in ("0x1", "0x2", "0x3", "0x4", "0x5"):
            self.assertEqual(filled_map[addr], rects[addr])

    def test_extend_last_cell_no_gap_when_bottom_row_adjacent(self):
        self._stub_rows(8, (1000, 600))
        rects, cell_map = self._grid_rects(8)
        targets = [(addr, *rect) for addr, rect in rects.items()]
        filled = w.extend_last_cell(None, targets, cell_map, "vertical")
        filled_map = {addr: (x, y, w, h) for addr, x, y, w, h in filled}

        self.assertEqual(filled_map["0x8"], rects["0x8"])
        self.assertNotEqual(filled_map["0x6"], rects["0x6"])

    def test_apply_fill_in_place_vertical_stretches_both_tiles(self):
        self._stub_rows(10, (1000, 600))
        rects, cell_map = self._grid_rects(10)

        updated, state = w.apply_fill_in_place(
            None, 1, "vertical", rects, cell_map, (None, None)
        )

        self.assertEqual(state[0], "vertical")
        self.assertIn("0x8", state[1])
        self.assertIn("0xa", state[1])
        self.assertEqual(
            updated["0xa"][0] + updated["0xa"][2],
            updated["0x8"][0] - w.GRID_GAP,
        )

    def test_apply_fill_horizontal_to_vertical_does_not_overlap(self):
        self._stub_rows(7, (1000, 600))
        rects, cell_map = self._grid_rects(7)

        horiz_rects, horiz_state = w.apply_fill_in_place(
            None, 1, "horizontal", rects, cell_map, (None, None)
        )
        vert_rects, vert_state = w.apply_fill_in_place(
            None, 1, "vertical", horiz_rects, cell_map, horiz_state
        )

        pad = w.GAPS_OUT + w.BORDER
        bottom = int(round(w.geometry(None)["t"] + pad + w.geometry(None)["h"] - 2 * pad))
        self.assertEqual(vert_rects["0x7"][1] + vert_rects["0x7"][3],
                         rects["0x7"][1] + rects["0x7"][3])
        self.assertEqual(vert_rects["0x7"][0] + vert_rects["0x7"][2],
                         vert_rects["0x6"][0] - w.GRID_GAP)
        self.assertEqual(vert_rects["0x6"][1] + vert_rects["0x6"][3], bottom)
        self.assertEqual(vert_state[0], "vertical")
        self.assertIn("0x6", vert_state[1])
        self.assertIn("0x7", vert_state[1])

    def test_apply_fill_off_restores_both_stretched_tiles(self):
        self._stub_rows(10, (1000, 600))
        rects, cell_map = self._grid_rects(10)
        updated, state = w.apply_fill_in_place(
            None, 1, "vertical", rects, cell_map, (None, None)
        )

        off_updated, off_state = w.apply_fill_in_place(
            None, 1, "off", updated, cell_map, state
        )

        self.assertEqual(off_state, (None, None))
        self.assertEqual(off_updated, rects)

    def test_logical_target_ignores_unoccupied_space_to_right(self):
        rects = {"0x1": (0, 0, 300, 300), "0x2": (318, 0, 618, 300)}
        cells = {"0x1": 0, "0x2": 1}

        self.assertEqual(w.logical_swap_target(rects, cells, "0x1", "right"), "0x2")
        self.assertIsNone(w.logical_swap_target(rects, cells, "0x2", "right"))

    def test_keyboard_swap_is_detected_as_two_position_changes(self):
        rects, _ = grid()
        original = w.current_rows
        w.current_rows = lambda _mon, _ws: [
            {"address": "0x4", "at": [318, 318], "size": [500, 300]},
            {"address": "0x5", "at": [0, 318], "size": [200, 300]},
        ]
        self.addCleanup(lambda: setattr(w, "current_rows", original))

        self.assertEqual(w.moved_layout(None, 1, rects), {"0x4", "0x5"})

    def test_size_only_change_is_not_detected_as_movement(self):
        rects, _ = grid()
        original = w.current_rows
        w.current_rows = lambda _mon, _ws: [
            {"address": "0x5", "at": [318, 318], "size": [500, 300]},
        ]
        self.addCleanup(lambda: setattr(w, "current_rows", original))

        self.assertEqual(w.moved_layout(None, 1, rects), set())

    def test_anchored_resize_is_one_position_change_not_a_swap(self):
        rects, _ = grid()
        original = w.current_rows
        w.current_rows = lambda _mon, _ws: [
            {"address": "0x5", "at": [268, 318], "size": [400, 300]},
        ]
        self.addCleanup(lambda: setattr(w, "current_rows", original))

        self.assertEqual(w.moved_layout(None, 1, rects), {"0x5"})


if __name__ == "__main__":
    unittest.main()
