import unittest

from zoomies_shell import addresses


class FixedTest(unittest.TestCase):
    def test_a_home_network_needs_no_mask(self):
        self.assertEqual(
            addresses.fixed("192.168.1.50", "192.168.1.1", "1.1.1.1, 8.8.8.8"),
            {
                "address": "192.168.1.50",
                "prefix": 24,
                "gateway": "192.168.1.1",
                "dns": ["1.1.1.1", "8.8.8.8"],
            },
        )

    def test_a_mask_is_kept(self):
        self.assertEqual(addresses.fixed(" 10.0.3.4/16 ")["prefix"], 16)

    def test_router_and_dns_are_optional(self):
        self.assertEqual(
            addresses.fixed("10.0.0.2"),
            {"address": "10.0.0.2", "prefix": 24, "gateway": None, "dns": []},
        )

    def test_dns_may_be_split_by_spaces(self):
        servers = addresses.fixed("10.0.0.2", dns="1.1.1.1 9.9.9.9")["dns"]
        self.assertEqual(servers, ["1.1.1.1", "9.9.9.9"])

    def test_mistakes_are_refused(self):
        for address, gateway, dns in (
            ("", "", ""),
            ("192.168.1", "", ""),
            ("192.168.1.300", "", ""),
            ("192.168.1.50/40", "", ""),
            ("fe80::1", "", ""),
            # The network's own address and its broadcast.
            ("192.168.1.0", "", ""),
            ("192.168.1.255", "", ""),
            ("192.168.1.50", "router", ""),
            ("192.168.1.50", "192.168.2.1", ""),
            ("192.168.1.50", "192.168.1.50", ""),
            ("192.168.1.50", "", "1.1.1.1, dns.example"),
        ):
            with self.subTest(address=address, gateway=gateway, dns=dns):
                with self.assertRaises(addresses.Invalid):
                    addresses.fixed(address, gateway, dns)


if __name__ == "__main__":
    unittest.main()
