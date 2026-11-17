import datetime
import unittest

from zoomies_shell import state

# A Monday.
MONDAY = datetime.date(2026, 11, 16)


def at(day, hhmm, second=0):
    """A time on the day `day` days after MONDAY."""
    h, m = map(int, hhmm.split(":"))
    date = MONDAY + datetime.timedelta(days=day)
    return datetime.datetime(date.year, date.month, date.day, h, m, second)


def usage(minutes=0, user="ana"):
    return {"date": "", "seconds": {user: minutes * 60}}


def day(*blocks, minutes=None):
    return {"blocks": [list(b) for b in blocks], "minutes": minutes}


def schedule(days, **rules):
    return {"kids": {"ana": {"schedule": {"days": days}, **rules}}}


SCHOOL = day(("07:00", "07:30"), ("17:00", "19:30"), minutes=60)
WEEKEND = day(("09:00", "12:00"), ("14:00", "20:00"), minutes=180)
WEEK = [SCHOOL] * 5 + [WEEKEND, None]
KID = {"user": "ana", "kind": "little"}


class Blocks(unittest.TestCase):
    def test_overlapping_and_touching_blocks_join(self):
        self.assertEqual(
            state.merge_blocks([(600, 700), (60, 120), (650, 800), (120, 180), (900, 900)]),
            [(60, 180), (600, 800)],
        )

    def test_times_of_day_are_checked(self):
        self.assertEqual(state.minutes_of_day("24:00"), 1440)
        for bad in ("24:30", "12:60", "-1:00"):
            with self.assertRaises(ValueError):
                state.minutes_of_day(bad)

    def test_days_round_trip(self):
        self.assertEqual(state.day_to_json(state.day_from_json(SCHOOL)), SCHOOL)
        self.assertIsNone(state.day_from_json(None))


class Week(unittest.TestCase):
    def test_without_a_schedule_every_day_follows_the_old_rules(self):
        kid = {**KID, "dailyMinutes": 60, "hours": {"start": "08:00", "end": "20:00"}}
        self.assertEqual(state.week(kid, {}), [{"blocks": [(480, 1200)], "minutes": 60}] * 7)

    def test_panel_rules_override_the_configuration(self):
        kid = {**KID, "dailyMinutes": 60}
        policy = {"kids": {"ana": {"dailyMinutes": 30}}}
        self.assertEqual(state.week(kid, policy)[0]["minutes"], 30)

    def test_old_hours_past_midnight_split_in_two(self):
        kid = {**KID, "hours": {"start": "20:00", "end": "02:00"}}
        self.assertEqual(state.week(kid, {})[0]["blocks"], [(0, 120), (1200, 1440)])

    def test_a_schedule_needs_seven_days(self):
        with self.assertRaises(ValueError):
            state.week(KID, schedule([SCHOOL] * 6))


class Status(unittest.TestCase):
    def status(self, policy, when, played=0):
        return state.kid_status(KID, policy, usage(played), when)

    def test_inside_a_block_counts_down_to_its_end(self):
        status = self.status(schedule(WEEK), at(0, "17:00"))
        self.assertTrue(status["allowed"])
        self.assertEqual(status["remaining"], 60 * 60)
        status = self.status(schedule(WEEK), at(0, "19:00", 30))
        self.assertEqual(status["remaining"], 29 * 60 + 30)

    def test_between_blocks_opens_at_the_next_block(self):
        status = self.status(schedule(WEEK), at(0, "08:00"))
        self.assertFalse(status["allowed"])
        self.assertEqual(
            (status["reason"], status["opensIn"], status["opensAt"]), ("hours", 0, "17:00")
        )

    def test_after_the_last_block_opens_tomorrow(self):
        status = self.status(schedule(WEEK), at(4, "21:00"))
        self.assertEqual(
            (status["reason"], status["opensIn"], status["opensAt"]), ("hours", 1, "09:00")
        )

    def test_a_day_without_play_skips_to_the_next_day_with_play(self):
        status = self.status(schedule(WEEK), at(6, "10:00"))
        self.assertEqual(
            (status["reason"], status["opensIn"], status["opensAt"]), ("day", 1, "07:00")
        )

    def test_zero_minutes_is_no_play(self):
        days = [day(("00:00", "24:00"), minutes=0)] * 7
        self.assertEqual(self.status(schedule(days), at(0, "10:00"))["reason"], "budget")

    def test_the_budget_ends_the_day(self):
        status = self.status(schedule(WEEK), at(0, "17:30"), played=60)
        self.assertEqual(
            (status["reason"], status["opensIn"], status["opensAt"]), ("budget", 1, "07:00")
        )

    def test_bonus_adds_to_the_budget(self):
        policy = schedule([SCHOOL] * 7)
        policy["bonus"] = {state.today(): {"ana": 15}}
        evening = datetime.datetime.combine(datetime.date.today(), datetime.time(18, 0))
        status = state.kid_status(KID, policy, usage(60), evening)
        self.assertEqual(status["remaining"], 15 * 60)

    def test_the_budget_counts_down_before_the_block_ends(self):
        status = self.status(schedule(WEEK), at(0, "17:00"), played=40)
        self.assertEqual(status["remaining"], 20 * 60)

    def test_stopped_for_today(self):
        policy = schedule([day(("00:00", "24:00"))] * 7)
        policy["stopped"] = {state.today(): {"ana": True}}
        status = state.kid_status(KID, policy, usage())
        self.assertEqual(
            (status["reason"], status["opensIn"], status["opensAt"]), ("stopped", 1, "00:00")
        )

    def test_all_day_without_a_cap_has_no_limit(self):
        status = self.status({}, at(0, "03:00"))
        self.assertEqual((status["allowed"], status["remaining"]), (True, None))

    def test_play_goes_on_past_midnight_when_the_next_day_starts_at_once(self):
        kid = {**KID, "hours": {"start": "20:00", "end": "02:00"}}
        status = state.kid_status(kid, {}, usage(), at(0, "23:00"))
        self.assertEqual(status["remaining"], 3 * 60 * 60)

    def test_special_days_play_like_another_weekday_or_not_at_all(self):
        policy = schedule(WEEK, special={MONDAY.isoformat(): 5})
        self.assertTrue(self.status(policy, at(0, "10:00"))["allowed"])
        policy = schedule(WEEK, special={MONDAY.isoformat(): "off"})
        status = self.status(policy, at(0, "17:00"))
        self.assertEqual((status["reason"], status["opensIn"]), ("day", 1))

    def test_a_broken_special_day_is_an_error(self):
        for like in (7, True, "monday"):
            with self.assertRaises(ValueError):
                self.status(schedule(WEEK, special={MONDAY.isoformat(): like}), at(0, "10:00"))

    def test_never_opening_again_says_so(self):
        status = self.status(schedule([None] * 7), at(0, "10:00"))
        self.assertEqual(
            (status["allowed"], status["opensIn"], status["opensAt"]), (False, None, None)
        )


class Broken(unittest.TestCase):
    """Rules of the wrong shape allow nothing; they never mean no limits."""

    def test_wrong_shapes_are_errors(self):
        for rules in (
            {"schedule": []},
            {"schedule": {"days": "everyday"}},
            {"schedule": {"days": [{"blocks": "all"}] * 7}},
            {"schedule": {"days": [{"blocks": [["09:00"]]}] * 7}},
            {"schedule": {"days": [{"blocks": [], "minutes": "60"}] * 7}},
            {"schedule": {"days": [{"blocks": [], "minutes": True}] * 7}},
            {"special": []},
            {"dailyMinutes": "lots"},
            {"hours": "08:00-20:00"},
        ):
            with self.subTest(rules=rules), self.assertRaises(ValueError):
                state.kid_status(KID, {"kids": {"ana": rules}}, usage(), at(0, "10:00"))
        with self.assertRaises(ValueError):
            state.kid_status(KID, {"kids": []}, usage(), at(0, "10:00"))

    def test_internet_needs_real_booleans(self):
        for rules in (
            {"on": "false", "days": [True] * 7},
            {"on": True, "days": ["false"] * 7},
            {"on": True, "days": [True] * 6},
        ):
            with self.subTest(rules=rules), self.assertRaises(ValueError):
                state.online(KID, {"kids": {"ana": {"internet": rules}}}, True, at(0, "10:00"))

    def test_a_damaged_policy_file_is_an_error_a_missing_one_is_not(self):
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            path = state.POLICY
            state.POLICY = f"{directory}/policy.json"
            try:
                self.assertEqual(state.load_policy(), {"kids": {}, "bonus": {}})
                for text in ("{broken", "[]"):
                    with open(state.POLICY, "w") as f:
                        f.write(text)
                    with self.assertRaises(state.BrokenPolicy):
                        state.load_policy()
            finally:
                state.POLICY = path


class Grid(unittest.TestCase):
    def test_blocks_stay_inside_the_day(self):
        self.assertEqual(state.clamp_block(1440, 1440), (1410, 1440))
        self.assertEqual(state.clamp_block(-30, 20), (0, 30))
        self.assertEqual(state.clamp_block(600, 2000), (600, 1440))

    def test_a_week_that_cannot_be_read_back_is_not_saved(self):
        with self.assertRaises(ValueError):
            state.save_week("ana", [{"blocks": [(1440, 1470)], "minutes": None}] * 7)

    def test_moving_a_block_on_every_weekday_moves_it_there_too(self):
        days = [state.day_from_json(SCHOOL)] * 5 + [state.day_from_json(WEEKEND), None]
        # Shorten 17:00-19:30 to 18:00-19:30 on every weekday.
        moved = state.retime(days, 0, 1, (18 * 60, 19 * 60 + 30), range(5))
        for day in moved[:5]:
            self.assertEqual(day["blocks"], [(420, 450), (1080, 1170)])
        self.assertEqual(moved[5:], days[5:])

    def test_a_day_without_that_block_gets_it_added(self):
        days = [state.day_from_json(SCHOOL), {"blocks": [(60, 120)], "minutes": None}]
        moved = state.retime(days, 0, 1, (18 * 60, 19 * 60), [0, 1])
        self.assertEqual(moved[1]["blocks"], [(60, 120), (1080, 1140)])


class Internet(unittest.TestCase):
    def test_little_kids_are_offline_and_older_kids_online_by_default(self):
        self.assertFalse(state.online(KID, {}, True, at(0, "10:00")))
        self.assertTrue(state.online({**KID, "kind": "older"}, {}, True, at(0, "10:00")))

    def test_only_while_playing(self):
        self.assertFalse(state.online({**KID, "kind": "older"}, {}, False, at(0, "10:00")))

    def test_only_on_the_chosen_days(self):
        rules = {"on": True, "days": [False] * 5 + [True, True]}
        policy = {"kids": {"ana": {"internet": rules}}}
        self.assertFalse(state.online(KID, policy, True, at(0, "10:00")))
        self.assertTrue(state.online(KID, policy, True, at(5, "10:00")))

    def test_special_days_follow_the_day_they_play_like(self):
        rules = {"on": True, "days": [False] * 5 + [True, True]}
        policy = {"kids": {"ana": {"internet": rules, "special": {MONDAY.isoformat(): 6}}}}
        self.assertTrue(state.online(KID, policy, True, at(0, "10:00")))

    def test_opened_for_a_while_even_when_not_playing(self):
        policy = {"internetUntil": {"ana": at(0, "11:00").isoformat()}}
        self.assertTrue(state.online(KID, policy, False, at(0, "10:59")))
        self.assertFalse(state.online(KID, policy, True, at(0, "11:00")))


if __name__ == "__main__":
    unittest.main()
