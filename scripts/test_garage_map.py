r"""Offline checks for the .gtr / .gmt readers and the garage-wall prediction (needs the game folder's Anderstorp files, no game running).

Run: scripts\.venv\Scripts\python.exe -I scripts\test_garage_map.py
The Anderstorp 3 case is the one measured in the game on 2026-11-14: driving straight out of the player's box hits the pillar between the
two bays (x -348.0, z -30.9) and a yaw bias of -6 degrees clears it (24 of 24 cars passed with -6, +6 drove into a wall).
"""
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "gtr2_driving"))
sys.path.insert(0, str(HERE))
from gtr2_ui import diag  # noqa: E402

ROOT = diag.game_root()
LOC = ROOT / "GameData" / "Locations" / "Anderstorp"
needs_game = unittest.skipUnless((LOC / "Anderstorp.gtr").exists(), "Anderstorp files not in the game folder")


@needs_game
class GarageMap(unittest.TestCase):
    def test_archive_lists_and_unpacks(self):
        import mas
        m = mas.Mas(LOC / "Anderstorp.gtr")
        self.assertEqual(m.count, 697)
        self.assertIn("PITWALLCOLLIDE.GMT", m.entries)
        self.assertEqual(len(m.read("PITWALLCOLLIDE.GMT")), 5076)

    def test_mesh_parses(self):
        import gmt
        import mas
        mesh = gmt.parse(mas.Mas(LOC / "Anderstorp.gtr").read("PITWALLCOLLIDE.GMT"))[0]
        self.assertEqual((len(mesh["vertices"]), len(mesh["triangles"])), (12, 6))
        xs = [v[0] for v in mesh["vertices"]]
        self.assertTrue(-517.3 < min(xs) < -517.0 and -314.6 < max(xs) < -314.4)

    def test_pillar_hit_and_bias_clear(self):
        import garage
        obs, floor = garage.obstacles(LOC / "3ANDERSTORP.trk", (-349.6, -35.4))
        self.assertAlmostEqual(floor, -2.95, delta=0.05)
        self.assertLess(garage.swept_clearance(obs, (-349.6, -35.4), -178.0, 0.0), 0)       # straight out: the pillar
        self.assertLess(garage.swept_clearance(obs, (-349.6, -35.4), -178.0, 6.0), 0)       # +6 drove into a wall
        self.assertGreater(garage.swept_clearance(obs, (-349.6, -35.4), -178.0, -6.0), 0.05)
        (gap, best), _rows = garage.best_bias(obs, (-349.6, -35.4), -178.0)
        self.assertTrue(-8 <= best <= -3 and gap > 0.05)


if __name__ == "__main__":
    unittest.main()
