from pathlib import Path
import sys
import unittest


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / 'src' / 'car_app_bridge'
sys.path.insert(0, str(PACKAGE_ROOT))

from car_app_bridge.control_lease import ControlLeaseManager, LeaseError


class TestControlLeaseManager(unittest.TestCase):
    def test_one_client_can_acquire_and_renew(self):
        manager = ControlLeaseManager(1.0)
        lease = manager.acquire('client-a', 10.0)
        renewed = manager.heartbeat('client-a', lease.lease_id, 10.5)

        self.assertEqual(renewed.lease_id, lease.lease_id)
        self.assertEqual(manager.snapshot(10.5)['active'], True)
        self.assertGreater(manager.snapshot(10.5)['expires_in_sec'], 0.9)

    def test_second_client_cannot_take_an_active_lease(self):
        manager = ControlLeaseManager(1.0)
        manager.acquire('client-a', 10.0)

        with self.assertRaises(LeaseError):
            manager.acquire('client-b', 10.1)
        with self.assertRaises(LeaseError):
            manager.release('client-b', None, 10.1)

    def test_expiry_allows_new_client_and_invalidates_old_lease(self):
        manager = ControlLeaseManager(1.0)
        lease = manager.acquire('client-a', 10.0)

        self.assertTrue(manager.expire(11.0))
        self.assertEqual(manager.snapshot(11.0), {'active': False})
        with self.assertRaises(LeaseError):
            manager.heartbeat('client-a', lease.lease_id, 11.0)

        replacement = manager.acquire('client-b', 11.0)
        self.assertNotEqual(replacement.lease_id, lease.lease_id)

    def test_release_requires_matching_lease_when_supplied(self):
        manager = ControlLeaseManager(1.0)
        lease = manager.acquire('client-a', 10.0)

        with self.assertRaises(LeaseError):
            manager.release('client-a', 'wrong', 10.1)
        self.assertTrue(manager.release('client-a', lease.lease_id, 10.1))
        self.assertFalse(manager.release('client-a', None, 10.2))


if __name__ == '__main__':
    unittest.main()
