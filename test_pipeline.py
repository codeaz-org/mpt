#!/usr/bin/env python3
"""Regression tests for the autopilot flow.

No network, no API keys, no MoneyPrinterTurbo checkout: every external call is stubbed.
The point is to prove the wiring still holds -- that a run reaches MPT with the right
arguments, that each failing dependency degrades instead of killing the run, and that
DRY_RUN never uploads.

Run: python3 test_pipeline.py
"""
import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

os.environ.pop("DRY_RUN", None)

import autopilot  # noqa: E402
import buffer  # noqa: E402
import critic  # noqa: F401,E402
import questions  # noqa: E402
import llm  # noqa: E402
import repos  # noqa: E402
import research  # noqa: E402

SCRIPT = ("Two waiters just sold the same table twice. Picture a Friday night restaurant "
          "with one table left and a paper reservation book. Each waiter is a thread. The "
          "last table is the shared resource. The book is your database row. A lock is the "
          "rule that only one waiter touches it. Skip it and two customers are charged for "
          "one seat, which is a duplicate payment under load. Lock the row.")

NICHE = {
    "id": "codeaz", "name": "CodeAZ", "voice": "en-GB-RyanNeural-Male",
    "topic_prompt": "topics", "hashtags": "#programming #coding",
    "youtube_tags": ["programming"], "videos_per_run": 1, "video_mode": "stock",
}


class Response:
    def __init__(self, status=200, payload=None, text="{}"):
        self.status_code, self._payload, self.text = status, payload or {}, text
        self.ok = status < 400
        self.headers = {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if not self.ok:
            import requests
            raise requests.HTTPError(f"{self.status_code}", response=self)


def chat_payload(content):
    return {"choices": [{"finish_reason": "stop", "message": {"content": content}}]}


class LlmClientTest(unittest.TestCase):
    def test_reasoning_model_null_content_grows_budget(self):
        """gpt-oss returns content: null when reasoning eats the token budget."""
        budgets = []

        def post(url, **kw):
            budgets.append(kw["json"]["max_tokens"])
            if len(budgets) < 3:
                return Response(200, {"choices": [{"finish_reason": "length", "message": {
                    "content": None, "reasoning_content": "thinking"}}]})
            return Response(200, chat_payload("done"))

        with mock.patch.object(llm.requests, "post", post), mock.patch.object(llm.time, "sleep"):
            self.assertEqual(llm.nim_chat("s", "u"), "done")
        self.assertEqual(budgets, [512, 2048, 8000])

    def test_timeout_is_retried(self):
        import requests
        calls = []

        def post(url, **kw):
            calls.append(1)
            if len(calls) < 2:
                raise requests.Timeout("read timed out")
            return Response(200, chat_payload("recovered"))

        with mock.patch.object(llm.requests, "post", post), mock.patch.object(llm.time, "sleep"):
            self.assertEqual(llm.nim_chat("s", "u"), "recovered")

    def test_json_helper_survives_prose_around_the_object(self):
        payload = chat_payload('Sure, here you go:\n```json\n{"topic": "x"}\n```')
        with mock.patch.object(llm.requests, "post", lambda *a, **k: Response(200, payload)):
            self.assertEqual(llm.nim_json("s", "u"), {"topic": "x"})


class ScriptQualityTest(unittest.TestCase):
    def test_drift_terms_are_per_niche(self):
        """A finance script must not be judged against programming vocabulary."""
        finance = {"id": "moneymech", "drift_terms": ["crypto", "day trading", "get rich"]}
        hype = ("Your savings account is like a bucket. Put crypto in it and day trading "
                "will get rich fast, guaranteed.")
        self.assertTrue(autopilot._drift_terms(hype, "Compound interest", finance))
        # the programming list must not fire on a finance topic
        threads = "Each teller is a thread holding a lock on the shared resource."
        self.assertEqual(autopilot._drift_terms(threads, "Compound interest", finance), [])

    def test_dormant_niche_is_skipped_not_failed(self):
        """A configured niche whose channel does not exist yet must not fail the run."""
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(autopilot.niche_is_ready({"id": "moneymech"}))
        with mock.patch.dict(os.environ, {"YT_REFRESH_TOKEN_MONEYMECH": "1//real"}):
            self.assertTrue(autopilot.niche_is_ready({"id": "moneymech"}))
        with mock.patch.dict(os.environ, {"YT_REFRESH_TOKEN_MONEYMECH": "xxxx"}):
            self.assertFalse(autopilot.niche_is_ready({"id": "moneymech"}))

    def test_every_configured_niche_has_the_required_fields(self):
        niches = json.loads((Path(__file__).parent / "niches.json").read_text())["niches"]
        for n in niches:
            self.assertIn("id", n)
            self.assertIn("name", n)
            self.assertIn("hashtags", n)
            if n.get("content_type") == "images":
                for field in ("images_per_video", "min_images", "captions", "ai_disclosure"):
                    self.assertIn(field, n, f"{n['id']} is missing {field}")
                continue
            for field in ("voice", "video_mode"):
                self.assertIn(field, n, f"{n.get('id')} is missing {field}")
            # A niche must tell the model what to write about. The original
            # `topic_prompt` was split into `select_prompt` + `script_prompt` when
            # topics started coming from harvested questions instead of a single
            # invent-a-topic call; either shape is accepted.
            self.assertTrue(
                n.get("topic_prompt") or (n.get("select_prompt") and n.get("script_prompt")),
                f"{n.get('id')} is missing topic_prompt (or select_prompt + script_prompt)")
            self.assertTrue(n["voice"].endswith(("-Male", "-Female")),
                            f"{n['id']} voice must carry the gender suffix MPT expects")
            self.assertIn("Neural", n["voice"], f"{n['id']} voice must be a real edge-tts id")

    def test_offtopic_concurrency_terms_are_rejected(self):
        drifted = ("A drive-thru is like a program. The cashier is the main thread and the "
                   "menu board is the API. The last car is the shared resource, which causes "
                   "a deadlock under load, and that is a race condition you must lock.")
        terms = autopilot._drift_terms(drifted, "Loops explained like a coffee shop drive-thru")
        self.assertGreater(len(terms), autopilot.MAX_DRIFT, f"drift not detected: {terms}")

    def test_concurrency_terms_allowed_when_topic_is_concurrency(self):
        self.assertEqual(
            autopilot._drift_terms(SCRIPT, "Race conditions, explained by two waiters"), [])

    def _approve(self):
        return mock.patch.object(critic, "review",
                                 lambda *a, **k: ("publish", {"hook": 9}, [], ""))

    def test_regenerates_until_on_topic(self):
        bad = ("A drive-thru is like a program. The cashier is the main thread. The menu is "
               "the API. The last car is the shared resource and causes a deadlock. " * 3)
        good = ("A drive-thru is like a loop. Each car is an iteration. The lane is the "
                "condition. The window is the loop body. Miss the exit and it is an infinite "
                "loop, so the queue never clears and orders stall. Loops repeat until done. " * 4)
        replies = [bad, bad, good]
        with mock.patch.object(autopilot, "nim_chat", lambda *a, **k: replies.pop(0)), \
             self._approve():
            out = autopilot.generate_script("Loops explained like a drive-thru", NICHE)
        self.assertIn("iteration", out)
        self.assertEqual(autopilot._drift_terms(out, "Loops explained like a drive-thru"), [])

    def test_thinking_block_never_reaches_narration(self):
        cleaned = autopilot._clean_script("<think>plan: map waiter to thread</think>Each waiter is a thread.")
        self.assertNotIn("plan", cleaned)
        self.assertTrue(cleaned.startswith("Each waiter"))


USED_TOPICS = [
    "Loops explained like a coffee shop drive-thru",
    "Functions like a recipe book",
    "Variables like labeled kitchen jars",
    "Garbage collection explained by city recycling trucks on scheduled routes",
    "Deadlocks explained by two cars stuck on intersecting one-way bridges",
    "Why lazy functions stay idle, explained by a restaurant's order ticket system",
]


class TopicNoveltyTest(unittest.TestCase):
    """A researched topic once slipped through that was the same video as an earlier one
    in different words. Exact-match checking cannot see that."""

    def test_reworded_repeats_are_caught(self):
        for topic in [
            # the real regression: 77% identical phrasing to the lazy-functions video
            "Why your async function stalls, explained by a restaurant reservation system",
            "Loops explained like a coffee shop drive thru",       # punctuation only
            "Functions explained like a recipe book",              # one word added
            "Garbage collection, explained by recycling trucks on their routes",
        ]:
            clash, why = autopilot.too_similar(topic, USED_TOPICS)
            self.assertIsNotNone(clash, f"missed repeat: {topic}")

    def test_same_concept_with_a_new_analogy_is_still_a_repeat(self):
        for topic in [
            "Loops explained like a subway turnstile queue",
            "Garbage collection, explained by a hotel housekeeping rota",
            "Deadlocks, explained by two people in a narrow doorway",
        ]:
            clash, why = autopilot.too_similar(topic, USED_TOPICS)
            self.assertIsNotNone(clash, f"swapping the analogy is not a new video: {topic}")
            self.assertIn("concept", why)

    def test_genuinely_new_topics_pass(self):
        for topic in [
            "Database indexes, explained like a library card catalogue",
            "Cache invalidation, explained by a stale specials board",
            "Hash collisions, explained by two guests with the same locker key",
            "Why your API rate limits, explained by a nightclub door policy",
            "Type inference, explained like a librarian's catalog system",
            "Event bubbling, explained by a postal mail sorting office",
        ]:
            clash, why = autopilot.too_similar(topic, USED_TOPICS)
            self.assertIsNone(clash, f"false positive: {topic} vs {clash} ({why})")

    def test_topic_must_come_from_a_harvested_question(self):
        """Ideas come from humans: with no questions available the run stops rather than
        letting the model invent a subject."""
        niche = {**NICHE, "subreddits": ["learnprogramming"]}
        with mock.patch.dict(os.environ, {}, clear=True), \
             mock.patch.object(questions, "harvest", lambda n: []):
            with self.assertRaises(RuntimeError) as ctx:
                autopilot.pick_topic(niche, USED_TOPICS)
        self.assertIn("no unanswered questions", str(ctx.exception))

    def test_already_answered_questions_are_filtered(self):
        harvested = [
            {"id": "reddit:1", "title": "Why does my loop run forever?", "score": 9,
             "num_comments": 4, "url": "u1"},
            {"id": "reddit:2", "title": "How does a hash map find a key so fast?",
             "score": 12, "num_comments": 6, "url": "u2"},
        ]
        left = questions.unused(harvested, {"reddit:1"}, [], autopilot.too_similar)
        self.assertEqual([q["id"] for q in left], ["reddit:2"])

    def test_question_matching_an_existing_video_is_filtered(self):
        harvested = [{"id": "reddit:9", "title": "Functions like a recipe book",
                      "score": 9, "num_comments": 4, "url": "u"}]
        self.assertEqual(questions.unused(harvested, set(), USED_TOPICS,
                                          autopilot.too_similar), [])


class HookTest(unittest.TestCase):
    """The topic is itself a question, so the model kept opening by restating it. The
    critic scored that 6 forever without ever forcing a rewrite."""

    def test_weak_openers_are_caught(self):
        for opener in [
            "When normalizing RGB values, should you divide by 255 or 256?",
            "Have you ever wondered how a hash map works? It uses buckets.",
            "In this video we look at loops.",
            "Did you know your cache can lie?",
            "Let's talk about closures.",
            # hedged abstractions: statements that promise nothing
            "Using the wrong divisor can lead to inaccurate color representation.",
            "Choosing the right divisor is important for color accuracy.",
            "Race conditions can be tricky to debug.",
        ]:
            self.assertIsNotNone(autopilot.weak_hook(opener), opener)

    def test_real_hooks_pass(self):
        for opener in [
            "Divide by 256 and every colour in your app shifts one shade dark.",
            "Two waiters just sold the same table twice.",
            "Your cache is lying to you right now, and the fix is one line.",
            "Your loop never exits because the counter resets on every pass.",
        ]:
            self.assertIsNone(autopilot.weak_hook(opener), opener)

    def test_weak_opener_is_repaired_by_the_dedicated_hook_call(self):
        """One call cannot answer the question, map the analogy, stay accurate and land a
        hook -- the hook is what it drops. So the hook gets its own call."""
        sent = []

        def chat(system, user, **kw):
            sent.append(system)
            if "opening line" in system:
                return "Divide by 256 and every colour comes out one shade dark."
            return "Should you divide by 255 or 256? " + "word " * 120

        with mock.patch.object(autopilot, "nim_chat", chat), \
             mock.patch.object(critic, "review",
                               lambda *a, **k: ("publish", {"hook": 9}, [], "")):
            out = autopilot.generate_script("Divide RGB by 255 or 256?", NICHE)
        self.assertTrue(out.startswith("Divide by 256"), f"opener not replaced: {out[:60]}")
        self.assertIsNone(autopilot.weak_hook(out))
        self.assertTrue(any("opening line" in x for x in sent), "hook call never happened")

    def test_hook_rewrite_keeps_the_body_intact(self):
        script = "Should you divide by 255 or 256? The ruler has 256 marks. Divide by 255."
        with mock.patch.object(autopilot, "nim_chat",
                               lambda *a, **k: "Every colour comes out one shade dark."):
            out = autopilot._rewrite_hook(script, "topic")
        self.assertTrue(out.startswith("Every colour comes out one shade dark."))
        self.assertIn("The ruler has 256 marks.", out)

    def test_hook_rewrite_gives_up_rather_than_ruining_the_script(self):
        script = "Should you divide by 255 or 256? The ruler has 256 marks."
        with mock.patch.object(autopilot, "nim_chat", lambda *a, **k: "Have you ever wondered?"):
            out = autopilot._rewrite_hook(script, "topic", attempts=2)
        self.assertEqual(out, script, "a bad candidate must not replace the opener")


class CriticTest(unittest.TestCase):
    """A model asked to write and approve its own work approves nearly everything, so the
    critic is a separate call that can send a script back."""

    def test_low_score_forces_a_revision_even_if_the_verdict_says_publish(self):
        payload = {"scores": {"hook": 3, "accuracy": 9}, "verdict": "publish",
                   "problems": ["generic opener"], "fix": "Open with the failure."}
        with mock.patch.object(critic, "nim_json", lambda *a, **k: payload):
            verdict, scores, problems, fix = critic.review("t", "s")
        self.assertEqual(verdict, "revise")

    def test_loop_stops_as_soon_as_it_passes(self):
        drafts = []

        def write(feedback):
            drafts.append(feedback)
            return "draft " + str(len(drafts))

        verdicts = [("revise", {"hook": 4}, ["weak hook"], "open with the failure"),
                    ("publish", {"hook": 9}, [], "")]
        with mock.patch.object(critic, "review", lambda *a, **k: verdicts.pop(0)):
            script, verdict, scores = critic.refine("topic", write)
        self.assertEqual(verdict, "publish")
        self.assertEqual(len(drafts), 2)
        self.assertEqual(drafts[0], None, "first draft gets no feedback")
        self.assertIn("open with the failure", drafts[1], "the fix must reach the writer")

    def test_never_passing_returns_the_best_attempt_flagged_as_revise(self):
        with mock.patch.object(critic, "review",
                               lambda *a, **k: ("revise", {"hook": 4}, [], "sharper")):
            script, verdict, scores = critic.refine("topic", lambda f: "draft", rounds=2)
        self.assertEqual(verdict, "revise")

    def test_a_failing_critic_cannot_approve(self):
        with mock.patch.object(critic, "nim_json", mock.Mock(side_effect=RuntimeError("down"))):
            verdict, scores, problems, fix = critic.review("t", "s")
        self.assertEqual(verdict, "revise")

    def test_script_that_never_passes_is_not_published(self):
        with mock.patch.object(autopilot, "nim_chat", lambda *a, **k: "word " * 120), \
             mock.patch.object(critic, "review",
                               lambda *a, **k: ("revise", {"hook": 3}, ["weak"], "fix it")):
            with self.assertRaises(RuntimeError) as ctx:
                autopilot.generate_script("topic", NICHE)
        self.assertIn("never passed review", str(ctx.exception))


class QuestionHarvestTest(unittest.TestCase):
    def test_only_real_questions_survive(self):
        keep = [{"title": "Why does my loop run forever?"},
                {"title": "How does a hash map find a key so fast"},
                {"title": "Can someone explain closures"}]
        drop = [{"title": "Show HN: my new database"},
                {"title": "What laptop should I buy for coding"},   # off-topic shape
                {"title": "Rust 2.0 released"},
                {"title": "Should I quit my job to learn programming"}]
        for q in keep:
            self.assertTrue(questions.looks_like_a_question(q), q["title"])
        for q in drop:
            self.assertFalse(questions.looks_like_a_question(q), q["title"])

    def test_low_engagement_questions_are_dropped(self):
        posts = [{"title": "Why does my loop run forever?", "score": 0, "num_comments": 0,
                  "id": "a"},
                 {"title": "How does a hash map work?", "score": 5, "num_comments": 4,
                  "id": "b"}]
        with mock.patch.object(questions.research, "fetch_subreddit", lambda *a, **k: posts), \
             mock.patch.object(questions.research, "fetch_ask_hn", lambda *a, **k: []):
            got = questions.harvest({"id": "x", "subreddits": ["s"]})
        self.assertEqual([q["id"] for q in got], ["b"])

    def test_selection_must_come_from_the_shortlist(self):
        qs = [{"title": "Why does my loop run forever?", "url": "u", "id": "a"}]
        with mock.patch.object(questions, "nim_json",
                               lambda *a, **k: {"index": 7, "topic": "Something"}):
            with self.assertRaises(RuntimeError):
                questions.choose({"name": "n"}, qs)


class ResearchTest(unittest.TestCase):
    def test_arctic_shift_parses_and_filters(self):
        payload = {"data": [
            {"title": "Real post", "selftext": "body", "score": 42, "num_comments": 7},
            {"title": "Pinned", "selftext": "", "score": 10, "num_comments": 1, "stickied": True},
            {"title": "", "selftext": "", "score": 5, "num_comments": 0},
        ]}
        with mock.patch.object(research, "_get", lambda *a, **k: Response(200, payload)):
            posts = research.fetch_subreddit_arctic("learnprogramming")
        self.assertEqual([p["title"] for p in posts], ["Real post"])

    def test_all_sources_down_raises_so_caller_can_fall_back(self):
        niche = {"id": "codeaz", "name": "CodeAZ", "subreddits": ["x"], "hn_queries": [""],
                 "stackexchange_tags": ["python"]}
        boom = mock.Mock(side_effect=RuntimeError("down"))
        with mock.patch.object(research, "fetch_subreddit", boom), \
             mock.patch.object(research, "fetch_hn", boom), \
             mock.patch.object(research, "fetch_stackexchange", boom), \
             mock.patch.object(research.time, "sleep"):
            with self.assertRaises(RuntimeError):
                research.research_topic(niche, [])


def _item(full_name, stars, created_at):
    """A raw GitHub Search API row, as _normalise expects to receive one."""
    return {
        "full_name": full_name, "name": full_name.split("/")[-1],
        "owner": {"login": full_name.split("/")[0]},
        "description": "A self-hosted tool that replaces a paid subscription for small teams.",
        "html_url": f"https://github.com/{full_name}", "stargazers_count": stars,
        "created_at": created_at, "language": "Go", "topics": [],
    }


def repo(full_name="acme/thing", desc=None, stars=1200, age_days=30, **kw):
    """A normalised repo record as repos._normalise would produce one."""
    r = {
        "full_name": full_name, "name": full_name.split("/")[-1],
        "owner": full_name.split("/")[0],
        "description": desc if desc is not None else
        "Self-hosted invoicing app that sends, tracks and reconciles client invoices.",
        "url": f"https://github.com/{full_name}", "stars": stars,
        "language": "TypeScript", "topics": ["self-hosted", "invoicing"],
        "license": "MIT", "created_at": "2026-08-01T00:00:00Z",
        "pushed_at": "2026-09-01T00:00:00Z", "archived": False, "fork": False,
        "age_days": float(age_days), "stars_per_day": stars / age_days,
    }
    r.update(kw)
    return r


class StarRisingSourceTest(unittest.TestCase):
    """Star Rising sources videos from trending repos instead of from questions."""

    def test_repos_without_a_usable_description_are_dropped(self):
        self.assertTrue(repos.usable_description(repo()))
        self.assertFalse(repos.usable_description(repo(desc="")))
        self.assertFalse(repos.usable_description(repo(desc="A tool.")))
        self.assertFalse(repos.usable_description(repo(desc="https://example.com/docs/here/now")))
        # Non-Latin descriptions are good software and unnarratable in an English voice.
        self.assertFalse(repos.usable_description(
            repo(desc="一个用于管理发票的自托管应用程序，支持多种货币和自动对账功能")))

    def test_reading_material_is_not_a_product_video(self):
        self.assertTrue(repos.is_runnable_shape(repo()))
        for junk in ("Awesome self-hosted apps",
                     "A curated list of automation tools",
                     "Roadmap to becoming a backend developer",
                     "My dotfiles",
                     "System design interview questions"):
            self.assertFalse(repos.is_runnable_shape(repo(desc=junk)), junk)

    def test_velocity_ranks_ahead_of_raw_star_count(self):
        """A repo that took four years to reach 5,000 stars is not news."""
        payload = {"items": [
            {"full_name": "old/famous", "name": "famous", "owner": {"login": "old"},
             "description": "A self-hosted analytics dashboard for small business sites.",
             "stargazers_count": 5000, "created_at": "2022-01-01T00:00:00Z",
             "html_url": "u", "topics": [], "language": "Go"},
            {"full_name": "new/rising", "name": "rising", "owner": {"login": "new"},
             "description": "A self-hosted booking system that replaces per-seat scheduling apps.",
             "stargazers_count": 900, "created_at": "2026-08-25T00:00:00Z",
             "html_url": "u", "topics": [], "language": "Python"},
        ]}
        with mock.patch.object(repos, "_api_get", lambda *a, **k: payload), \
             mock.patch.object(repos.time, "sleep"):
            got = repos.fetch_candidates({"id": "codeaz", "star_rising": {"queries": [""]}})
        self.assertEqual([r["full_name"] for r in got], ["new/rising", "old/famous"])

    def test_each_query_is_represented_in_the_shortlist(self):
        """A global velocity sort hands all twenty rows to whatever is going viral
        that week; the niche's own queries have to survive into the shortlist."""
        payloads = {
            "": {"items": [_item(f"viral/hype{i}", 9000, "2026-09-01T00:00:00Z")
                           for i in range(5)]},
            "topic:self-hosted": {"items": [_item("small/selfhosted", 400,
                                                  "2026-08-01T00:00:00Z")]},
        }
        calls = []

        def fake_api(params, **kw):
            calls.append(params["q"])
            extra = params["q"].split("stars:>=300")[-1].strip()
            return payloads[extra]

        with mock.patch.object(repos, "_api_get", fake_api), \
             mock.patch.object(repos.time, "sleep"):
            got = repos.fetch_candidates(
                {"id": "codeaz", "star_rising": {"queries": ["", "topic:self-hosted"]}})
        names = [r["full_name"] for r in got]
        self.assertEqual(names[1], "small/selfhosted",
                         "the second slot belongs to the second query, not to rank 2 of the first")
        self.assertEqual(len(calls), 2)

    def test_already_covered_repos_are_never_covered_twice(self):
        candidates = [repo("acme/thing"), repo("other/tool")]
        fresh = repos.unused(candidates, {"ACME/Thing"})   # GitHub is case-insensitive
        self.assertEqual([r["full_name"] for r in fresh], ["other/tool"])

    def test_a_shortlist_with_nothing_worth_covering_raises(self):
        """-1 means the gate rejected every candidate; that must fall back, not publish."""
        with mock.patch.object(repos, "nim_json",
                               lambda *a, **k: {"index": -1, "why": "all research code"}):
            with self.assertRaises(RuntimeError):
                repos.choose({"name": "CodeAZ"}, [repo()])

    def test_selection_must_come_from_the_shortlist(self):
        with mock.patch.object(repos, "nim_json",
                               lambda *a, **k: {"index": 9, "topic": "Something"}):
            with self.assertRaises(RuntimeError):
                repos.choose({"name": "CodeAZ"}, [repo()])

    def test_posted_repos_reads_both_the_pick_log_and_the_uploads(self):
        state = {"repos": {"codeaz": ["a/one"]},
                 "uploads": [{"niche": "codeaz", "repo": "b/two"},
                             {"niche": "other", "repo": "c/three"}]}
        self.assertEqual(autopilot.posted_repos(state, "codeaz"), {"a/one", "b/two"})


class StarRisingAlternationTest(unittest.TestCase):
    NICHE = {"id": "codeaz", "star_rising": {"enabled": True, "every_other_run": True}}

    def test_disabled_niche_never_takes_the_repo_path(self):
        self.assertFalse(autopilot.star_rising_turn({"id": "codeaz"}, {}))
        self.assertFalse(autopilot.star_rising_turn(
            {"id": "codeaz", "star_rising": {"enabled": False}}, {}))

    def test_runs_alternate_with_the_question_pipeline(self):
        state = {}
        self.assertTrue(autopilot.star_rising_turn(self.NICHE, state))
        autopilot._record_mode(state, "codeaz", "star_rising")
        self.assertFalse(autopilot.star_rising_turn(self.NICHE, state))
        autopilot._record_mode(state, "codeaz", "question")
        self.assertTrue(autopilot.star_rising_turn(self.NICHE, state))

    def test_every_other_run_off_means_every_run(self):
        niche = {"id": "codeaz", "star_rising": {"enabled": True, "every_other_run": False}}
        state = {"modes": {"codeaz": ["star_rising"]}}
        self.assertTrue(autopilot.star_rising_turn(niche, state))


class StarRisingRenderTest(unittest.TestCase):
    def test_api_numbers_win_over_anything_the_model_extracted(self):
        """The star count on screen is GitHub's, never a rounded narration figure."""
        props = autopilot._repo_props(repo(stars=4210, age_days=30))
        self.assertEqual(props["repo"], "acme/thing")
        self.assertEqual(props["stars"], "4.2k")
        self.assertIn("TypeScript", props["starsNote"])
        self.assertIn("MIT", props["starsNote"])

    def test_extracted_tagline_beats_the_raw_description(self):
        captured = {}

        def fake_render(topic, niche, script, **kw):
            captured.update(kw)
            return "/tmp/v.mp4", "StarRising"

        module = mock.Mock(render=fake_render)
        with mock.patch.dict(sys.modules, {"remotion_render": module}), \
             mock.patch.object(autopilot, "check_rendered_video", lambda *a: None):
            autopilot.render_video(
                "topic", {"id": "codeaz", "video_mode": "remotion"}, "script",
                force_archetype="StarRising",
                base_props=autopilot._repo_props(repo()),
                fallback_props=autopilot._repo_fallback_props(repo()))
        self.assertEqual(captured["force_archetype"], "StarRising")
        self.assertEqual(captured["base_props"]["repo"], "acme/thing")
        # the raw description is a fallback, so a script-derived tagline wins
        self.assertIn("tagline", captured["fallback_props"])
        self.assertNotIn("tagline", captured["base_props"])

    def test_merge_precedence_api_over_script_over_source_text(self):
        import remotion_render
        merged = remotion_render.merge_props(
            {"tagline": "A tight line the writer produced.", "stars": "about 4,000",
             "replaces": ""},
            base_props={"repo": "acme/thing", "stars": "4.2k"},
            fallback_props={"tagline": "The raw GitHub description.",
                            "replaces": "A per-seat subscription"})
        # API value replaces the model's rounded one
        self.assertEqual(merged["stars"], "4.2k")
        self.assertEqual(merged["repo"], "acme/thing")
        # a script-derived line survives; an empty one gets the source text
        self.assertEqual(merged["tagline"], "A tight line the writer produced.")
        self.assertEqual(merged["replaces"], "A per-seat subscription")

    def test_merged_values_are_capped_to_their_on_screen_slot(self):
        import remotion_render
        merged = remotion_render.merge_props(
            {}, fallback_props={"tagline": "word " * 60})
        self.assertLessEqual(len(merged["tagline"]),
                             remotion_render._FIELD_CAPS["tagline"])

    def test_star_rising_is_hidden_from_the_classifier(self):
        """It is chosen by where the topic came from, not by how the script reads --
        a cost teardown must never be rendered with repo props it does not have."""
        import remotion_render
        self.assertIn("StarRising", remotion_render.ARCHETYPES)
        self.assertNotIn("StarRising", remotion_render._ARCH_DESCRIPTIONS)
        self.assertEqual(remotion_render.ARCHETYPE_TAGS["StarRising"], "RISING")

    def test_the_repo_is_credited_in_the_description(self):
        with mock.patch.object(autopilot, "nim_chat",
                               lambda *a, **k: '{"title": "T", "description": "D"}'):
            meta = autopilot.make_metadata("topic", NICHE, repo=repo())
        self.assertIn("https://github.com/acme/thing", meta["description"])


class StarRisingHookTest(unittest.TestCase):
    """Star Rising inverts the channel's hook rule: the segment sells "you can
    have this free", and the question is what makes a viewer stay for the answer."""

    def test_a_question_is_required_not_rejected(self):
        q = "Did you know there is a free Notion you can host yourself? It does X."
        self.assertIsNone(autopilot.weak_hook(q, style="question"))
        # the same opener still fails everywhere else
        self.assertIsNotNone(autopilot.weak_hook(q))

    def test_the_flat_opener_that_shipped_in_the_first_draft_is_caught(self):
        flat = "The project is firecrawl/anydoc. It converts documents."
        self.assertIsNotNone(autopilot.weak_hook(flat, style="question"))
        # ...and it slipped past the statement style, which is why it shipped
        self.assertIsNone(autopilot.weak_hook(flat))

    def test_statement_openers_are_still_the_default_everywhere_else(self):
        statement = "Zapier just charged you $29 to run 100 tasks. Here is why."
        self.assertIsNone(autopilot.weak_hook(statement))
        self.assertIsNotNone(autopilot.weak_hook(statement, style="question"))

    def test_the_rewrite_asks_for_a_question_and_keeps_the_body(self):
        script = "The project is acme/thing. It converts files. It costs nothing."
        with mock.patch.object(autopilot, "nim_chat",
                               lambda system, user, **kw:
                               "Did you know you can convert any PDF for free?"
                               if "FREE" in system else "A flat statement."):
            fixed = autopilot._rewrite_hook(script, "topic", style="question")
        self.assertTrue(fixed.startswith("Did you know"))
        self.assertIn("It converts files.", fixed)


class StarRisingMetadataTest(unittest.TestCase):
    def test_the_description_never_claims_someone_elses_project(self):
        """The first dry run described firecrawl's project as "our open-source tool"."""
        seen = {}
        with mock.patch.object(autopilot, "nim_chat",
                               lambda system, user, **kw:
                               seen.setdefault("system", system) and "" or
                               '{"title": "T", "description": "D"}'):
            autopilot.make_metadata("topic", NICHE, repo=repo())
        self.assertIn("did NOT build", seen["system"])
        self.assertIn("acme/thing", seen["system"])

    def test_ordinary_videos_get_no_credit_line(self):
        seen = {}
        with mock.patch.object(autopilot, "nim_chat",
                               lambda system, user, **kw:
                               seen.setdefault("system", system) and "" or
                               '{"title": "T", "description": "D"}'):
            autopilot.make_metadata("topic", NICHE)
        self.assertNotIn("did NOT build", seen["system"])


class StarRisingScreenshotTest(unittest.TestCase):
    def test_a_failed_capture_costs_the_shot_not_the_episode(self):
        import remotion_render
        with mock.patch.dict(sys.modules, {"screenshot": mock.Mock(
                capture=mock.Mock(side_effect=RuntimeError("no chrome")))}):
            self.assertEqual(remotion_render._capture_repo_page("https://x/y"), {})

    def test_a_capture_returns_the_dimensions_the_pan_needs(self):
        import remotion_render
        fake = mock.Mock(capture=mock.Mock(return_value=(1280, 5000)))
        with mock.patch.dict(sys.modules, {"screenshot": fake}):
            got = remotion_render._capture_repo_page("https://github.com/acme/thing")
        self.assertEqual(got, {"screenshot": "repo.png", "screenshotWidth": 1280,
                               "screenshotHeight": 5000})

    def test_png_header_parsing_matches_the_file(self):
        import screenshot
        png = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
               + (1280).to_bytes(4, "big") + (5000).to_bytes(4, "big"))
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(png)
        self.assertEqual(screenshot.png_size(f.name), (1280, 5000))
        os.unlink(f.name)


class StarRisingScriptTest(unittest.TestCase):
    def test_the_writer_only_gets_facts_the_api_returned(self):
        seen = {}

        def fake_chat(system, user, **kw):
            seen["system"] = system
            return "Narration."

        niche = {"id": "codeaz", "repo_script_prompt": "STAR RISING PROMPT",
                 "script_prompt": "QUESTION PROMPT"}
        with mock.patch.object(autopilot, "nim_chat", fake_chat):
            autopilot._write_script("topic", niche, repo=repo())
        self.assertIn("STAR RISING PROMPT", seen["system"])
        self.assertNotIn("QUESTION PROMPT", seen["system"])
        self.assertIn("acme/thing", seen["system"])
        self.assertIn("1,200", seen["system"])          # exact star count, not rounded
        self.assertIn("You have NOT run this project", seen["system"])

    def test_the_repo_prompt_demands_the_free_capability_question(self):
        cfg = json.loads((Path(__file__).parent / "niches.json").read_text())
        niche = cfg["niches"][0]
        prompt = niche["repo_script_prompt"]
        self.assertIn("question mark", prompt)
        self.assertIn("FREE", prompt)
        # the rubric has to agree with the prompt, or the critic reverts the hook
        rubric = niche["star_rising"]["critic_rubric"]
        self.assertIn("QUESTION", rubric)
        # A dry run described n8n -- a seven-year-old company project -- as having
        # thin docs and "a single maintainer". Neither is knowable from the brief.
        for banned in ("maintain", "documentation"):
            self.assertIn(banned, prompt.lower(),
                          "the prompt must forbid inventing maintainer/doc claims")
        self.assertIn("MAINTAINER COUNT", rubric)
        for axis in niche["star_rising"]["critic_axes"]:
            self.assertIn(axis, rubric, f"{axis} is scored but never described")

    def test_the_question_path_is_untouched_when_no_repo_is_given(self):
        seen = {}
        with mock.patch.object(autopilot, "nim_chat",
                               lambda system, user, **kw: seen.setdefault("system", system) and ""
                               or "Narration."):
            autopilot._write_script("topic", {"id": "codeaz",
                                              "repo_script_prompt": "STAR RISING PROMPT",
                                              "script_prompt": "QUESTION PROMPT"})
        self.assertIn("QUESTION PROMPT", seen["system"])
        self.assertNotIn("STAR RISING PROMPT", seen["system"])


class StaticCheckTest(unittest.TestCase):
    def test_no_undefined_names(self):
        """A NameError in write_mpt_config once killed a run after the script had already
        been generated -- it only fires when MPT is actually invoked, which no stubbed
        test reaches. pyflakes catches that class of bug without executing anything."""
        try:
            import pyflakes
            del pyflakes
        except ImportError:
            self.skipTest("pyflakes not installed (pip install pyflakes)")
        files = ["autopilot.py", "llm.py", "research.py", "repos.py",
                 "screenshot.py"]
        r = subprocess.run([sys.executable, "-m", "pyflakes", *files],
                           cwd=Path(__file__).parent, capture_output=True, text=True)
        undefined = [ln for ln in r.stdout.splitlines() if "undefined name" in ln]
        self.assertEqual(undefined, [], "undefined names:\n" + "\n".join(undefined))


class ConfigTest(unittest.TestCase):
    def test_written_config_has_model_voice_and_keys(self):
        """write_mpt_config interpolates module-level constants; exercise it for real."""
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(autopilot, "MPT_DIR", Path(tmp)), \
                 mock.patch.dict(os.environ, {"PEXELS_API_KEY": "pk", "PIXABAY_API_KEY": "xk",
                                              "NIM_API_KEY": "nk"}):
                autopilot.write_mpt_config(NICHE, "pexels")
            cfg = (Path(tmp) / "config.toml").read_text()
        self.assertIn('voice_name = "en-GB-RyanNeural-Male"', cfg)
        self.assertIn(f'openai_model_name = "{autopilot.NIM_MODEL}"', cfg)
        self.assertIn('video_source = "pexels"', cfg)
        self.assertIn('pexels_api_keys = ["pk"]', cfg)
        self.assertNotIn("{NIM", cfg, "every placeholder must be interpolated")

    def test_placeholder_keys_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(autopilot, "MPT_DIR", Path(tmp)), \
                 mock.patch.dict(os.environ, {"PEXELS_API_KEY": "xxxx", "PIXABAY_API_KEY": "",
                                              "NIM_API_KEY": "nk"}):
                autopilot.write_mpt_config(NICHE, "pexels")
                cfg = (Path(tmp) / "config.toml").read_text()
                self.assertIn('pexels_api_keys = [""]', cfg)
                with self.assertRaises(RuntimeError):
                    autopilot.pick_sources(NICHE)


class RenderedVideoCheckTest(unittest.TestCase):
    """A three second clip carrying only the opening line once reached a channel, and
    nothing between the renderer and the upload noticed."""

    SCRIPT = "word " * 150   # ~58s of narration

    def test_truncated_render_is_refused(self):
        with mock.patch.object(autopilot, "video_duration", lambda p: 3.0), \
             mock.patch.object(autopilot.subprocess, "run",
                               lambda *a, **k: mock.Mock(stdout="video\naudio\n")):
            with self.assertRaises(RuntimeError) as ctx:
                autopilot.check_rendered_video("/tmp/v.mp4", self.SCRIPT)
        self.assertIn("cut short", str(ctx.exception))

    def test_silent_video_is_refused(self):
        with mock.patch.object(autopilot, "video_duration", lambda p: 60.0), \
             mock.patch.object(autopilot.subprocess, "run",
                               lambda *a, **k: mock.Mock(stdout="video\n")):
            with self.assertRaises(RuntimeError) as ctx:
                autopilot.check_rendered_video("/tmp/v.mp4", self.SCRIPT)
        self.assertIn("no audio", str(ctx.exception))

    def test_a_healthy_render_passes(self):
        with mock.patch.object(autopilot, "video_duration", lambda p: 58.0), \
             mock.patch.object(autopilot.subprocess, "run",
                               lambda *a, **k: mock.Mock(stdout="video\naudio\n")):
            self.assertEqual(autopilot.check_rendered_video("/tmp/v.mp4", self.SCRIPT), 58.0)

    def test_short_but_proportionate_video_still_fails_the_floor(self):
        """Even a proportionate render is refused below the absolute floor: a 15s short
        is not what this pipeline is for."""
        with mock.patch.object(autopilot, "video_duration", lambda p: 15.0), \
             mock.patch.object(autopilot.subprocess, "run",
                               lambda *a, **k: mock.Mock(stdout="video\naudio\n")):
            with self.assertRaises(RuntimeError):
                autopilot.check_rendered_video("/tmp/v.mp4", "word " * 40)


class RenderTest(unittest.TestCase):
    def test_mpt_command_has_voice_and_subtitle_flags(self):
        captured = {}

        def run(cmd, **kw):
            captured["cmd"] = cmd
            return mock.Mock(returncode=0, stdout="", stderr="")

        with mock.patch.object(autopilot.subprocess, "run", run), \
             mock.patch.object(autopilot.glob, "glob", return_value=["/tmp/final-1.mp4"]), \
             mock.patch.object(autopilot.os.path, "getmtime", return_value=9e9):
            autopilot.generate_video("topic", NICHE, "pexels", script="s", terms="t")

        cmd = captured["cmd"]
        # The voice regression: MPT's CLI default overrides config.toml, so this flag
        # must always be present or narration reverts to Chinese.
        self.assertIn("--voice-name", cmd)
        self.assertEqual(cmd[cmd.index("--voice-name") + 1], "en-GB-RyanNeural-Male")
        for flag in ("--video-script", "--video-terms", "--font-name", "--font-size",
                     "--subtitle-position", "--custom-position", "--stroke-width"):
            self.assertIn(flag, cmd)
        # MPT's bundled background music draws YouTube copyright claims.
        self.assertEqual(cmd[cmd.index("--bgm-type") + 1], "none")
        self.assertEqual(cmd[cmd.index("--bgm-volume") + 1], "0")
        self.assertEqual(cmd[cmd.index("--font-name") + 1], "BeVietnamPro-Bold.ttf")

    def test_falls_back_to_other_stock_source(self):
        tried = []

        def gen(topic, niche, source, script=None, terms=None):
            tried.append(source)
            if len(tried) == 1:
                raise RuntimeError("MPT failed:\nstage=materials, error: failed to "
                                   "download video materials from pixabay")
            return "/tmp/final.mp4"

        with mock.patch.dict(os.environ, {"PEXELS_API_KEY": "a", "PIXABAY_API_KEY": "b"}), \
             mock.patch.object(autopilot, "generate_video", gen), \
             mock.patch.object(autopilot, "write_mpt_config", lambda *a: None):
            self.assertEqual(autopilot.render_with_fallback("t", NICHE, "s", "x"), "/tmp/final.mp4")
        self.assertEqual(len(tried), 2)

    def test_real_mpt_failure_is_not_retried(self):
        tried = []

        def gen(topic, niche, source, script=None, terms=None):
            tried.append(source)
            raise RuntimeError("MPT failed:\nffmpeg: invalid codec")

        with mock.patch.dict(os.environ, {"PEXELS_API_KEY": "a", "PIXABAY_API_KEY": "b"}), \
             mock.patch.object(autopilot, "generate_video", gen), \
             mock.patch.object(autopilot, "write_mpt_config", lambda *a: None):
            with self.assertRaises(RuntimeError):
                autopilot.render_with_fallback("t", NICHE, "s", "x")
        self.assertEqual(len(tried), 1, "a codec error must not burn the other source")

    def test_unknown_video_mode_is_rejected(self):
        with self.assertRaises(RuntimeError):
            autopilot.render_video("t", {**NICHE, "video_mode": "slideshow"}, "s")


class YouTubeCredentialsTest(unittest.TestCase):
    """Quota is per Cloud project, so a channel with its own Google account has its own
    OAuth client -- and a refresh token only works with the client that minted it."""

    def test_per_niche_client_overrides_the_shared_one(self):
        with mock.patch.dict(os.environ, {
                "YT_CLIENT_ID": "shared", "YT_CLIENT_SECRET": "shared-secret",
                "YT_CLIENT_ID_MONEYMECH": "own", "YT_CLIENT_SECRET_MONEYMECH": "own-secret",
                "YT_REFRESH_TOKEN_MONEYMECH": "tok"}, clear=True):
            self.assertEqual(autopilot.youtube_credentials("moneymech"),
                             ("own", "own-secret", "tok"))

    def test_falls_back_to_the_shared_client(self):
        with mock.patch.dict(os.environ, {
                "YT_CLIENT_ID": "shared", "YT_CLIENT_SECRET": "shared-secret",
                "YT_REFRESH_TOKEN_CODEAZ": "tok"}, clear=True):
            self.assertEqual(autopilot.youtube_credentials("codeaz"),
                             ("shared", "shared-secret", "tok"))

    def test_placeholder_refresh_token_counts_as_absent(self):
        with mock.patch.dict(os.environ, {"YT_REFRESH_TOKEN_AIWORKS": "xxxx"}, clear=True):
            self.assertEqual(autopilot.youtube_credentials("aiworks")[2], "")


class YouTubeUploadTest(unittest.TestCase):
    def test_upload_uses_public_privacy_and_no_synthetic_flag(self):
        """The upload no longer self-declares altered media -- the flag was removed
        by request. The body still ships public and not-for-kids."""
        captured = {}

        class Insert:
            def next_chunk(self):
                return None, {"id": "vid123"}

        class Videos:
            def insert(self, part, body, media_body):
                captured["body"] = body
                captured["part"] = part
                return Insert()

        class YT:
            def videos(self):
                return Videos()

        with mock.patch.dict("sys.modules", {
                "google.oauth2.credentials": mock.MagicMock(),
                "googleapiclient.discovery": mock.MagicMock(build=lambda *a, **k: YT()),
                "googleapiclient.http": mock.MagicMock(
                    MediaFileUpload=lambda *a, **k: object())}), \
             mock.patch.dict(os.environ, {"YT_CLIENT_ID": "i", "YT_CLIENT_SECRET": "s",
                                          "YT_REFRESH_TOKEN_CODEAZ": "r"}):
            autopilot.upload_youtube("/tmp/v.mp4",
                                     {"title": "T", "description": "D"}, NICHE)
        self.assertEqual(captured["body"]["status"]["privacyStatus"], "public")
        self.assertNotIn("containsSyntheticMedia", captured["body"]["status"])
        self.assertIn("status", captured["part"])


class TikTokCaptionTest(unittest.TestCase):
    def test_caption_merges_title_description_and_hashtags(self):
        meta = {"title": "Race conditions", "description": "Two waiters, one table."}
        caption = autopilot.tiktok_caption(meta, NICHE)
        self.assertIn("Race conditions", caption)
        self.assertTrue(caption.endswith(NICHE["hashtags"]))

    def test_long_caption_keeps_hashtags(self):
        meta = {"title": "T" * 80, "description": "D" * 4000}
        caption = autopilot.tiktok_caption(meta, NICHE)
        self.assertLessEqual(len(caption), 2200)
        self.assertTrue(caption.endswith(NICHE["hashtags"]),
                        "hashtags must survive truncation")


class BufferChannelRoutingTest(unittest.TestCase):
    """Several niches share one Buffer account, so the channel must be chosen per niche
    rather than guessed -- otherwise one niche's video reaches another's audience."""

    def _gql(self, channels):
        def gql(query, variables=None):
            if "account" in query:
                return {"account": {"organizations": [{"id": "org1"}]}}
            return {"channels": channels}
        return gql

    def test_per_niche_channel_env_wins(self):
        with mock.patch.dict(os.environ, {"BUFFER_CHANNEL_ID_AIWORKS": "ch-ai"}), \
             mock.patch.object(buffer, "gql", self._gql([])):
            self.assertEqual(buffer.tiktok_channel("aiworks")[0], "ch-ai")

    def test_several_channels_without_mapping_is_an_error(self):
        channels = [{"id": "a", "name": "codeaz", "service": "tiktok"},
                    {"id": "b", "name": "aiworks", "service": "tiktok"}]
        with mock.patch.dict(os.environ, {}, clear=True), \
             mock.patch.object(buffer, "gql", self._gql(channels)):
            with self.assertRaises(RuntimeError) as ctx:
                buffer.tiktok_channel("aiworks")
        self.assertIn("BUFFER_CHANNEL_ID_AIWORKS", str(ctx.exception))

    def test_single_channel_still_resolves(self):
        channels = [{"id": "only", "name": "codeaz", "service": "tiktok"}]
        with mock.patch.dict(os.environ, {}, clear=True), \
             mock.patch.object(buffer, "gql", self._gql(channels)):
            self.assertEqual(buffer.tiktok_channel("codeaz")[0], "only")


class BufferTest(unittest.TestCase):
    def test_publish_sends_caption_without_ai_flag(self):
        sent = {}

        def gql(query, variables=None):
            if "account" in query:
                return {"account": {"organizations": [{"id": "org1"}]}}
            if "channels" in query:
                return {"channels": [{"id": "ch1", "name": "codeazorg", "service": "tiktok"}]}
            sent["input"] = variables["input"]
            return {"createPost": {"__typename": "PostActionSuccess",
                                   "post": {"id": "post1", "dueAt": None}}}

        with mock.patch.object(buffer, "gql", gql):
            post_id = buffer.publish(None, "caption #tag", title="T",
                                     video_url="https://example.com/v.mp4")
        self.assertEqual(post_id, "post1")
        inp = sent["input"]
        self.assertEqual(inp["channelId"], "ch1")
        self.assertEqual(inp["text"], "caption #tag")
        self.assertEqual(inp["assets"], [{"video": {"url": "https://example.com/v.mp4"}}])
        self.assertEqual(inp["schedulingType"], "automatic")
        # queueing it put videos days out behind an existing backlog
        self.assertEqual(inp["mode"], "shareNow")
        # isAiGenerated was removed by request; ensure it does not sneak back
        self.assertNotIn("isAiGenerated", inp["metadata"]["tiktok"])

    def test_error_union_is_reported(self):
        def gql(query, variables=None):
            if "account" in query:
                return {"account": {"organizations": [{"id": "org1"}]}}
            if "channels" in query:
                return {"channels": [{"id": "ch1", "service": "tiktok"}]}
            return {"createPost": {"__typename": "InvalidInputError",
                                   "message": "Video could not be read from its URL."}}

        with mock.patch.object(buffer, "gql", gql):
            with self.assertRaises(RuntimeError) as ctx:
                buffer.publish(None, "c", video_url="https://example.com/bad.mp4")
        self.assertIn("could not be read", str(ctx.exception))

    def test_missing_tiktok_channel_is_explicit(self):
        def gql(query, variables=None):
            if "account" in query:
                return {"account": {"organizations": [{"id": "org1"}]}}
            return {"channels": [{"id": "c", "service": "mastodon"}]}

        with mock.patch.object(buffer, "gql", gql):
            with self.assertRaises(RuntimeError) as ctx:
                buffer.tiktok_channel()
        self.assertIn("no TikTok channel", str(ctx.exception))


class PublishDispatchTest(unittest.TestCase):
    def test_buffer_replaces_the_inbox_draft(self):
        with mock.patch.object(buffer, "enabled", lambda: True), \
             mock.patch.object(buffer, "publish",
                               lambda v, c, title=None, niche_id=None: "post1"), \
             mock.patch.object(autopilot, "upload_tiktok",
                               mock.Mock(side_effect=AssertionError("inbox must not run"))):
            ok, via, pid = autopilot.publish_tiktok("/tmp/v.mp4", {"title": "T"}, NICHE, "cap")
        self.assertEqual((ok, via, pid), (True, "buffer", "post1"))

    def test_buffer_failure_falls_back_to_inbox(self):
        def boom(*a, **k):
            raise RuntimeError("buffer down")

        with mock.patch.object(buffer, "enabled", lambda: True), \
             mock.patch.object(buffer, "publish", boom), \
             mock.patch.object(autopilot, "upload_tiktok", lambda v, m, n: "inbox1"):
            ok, via, pid = autopilot.publish_tiktok("/tmp/v.mp4", {"title": "T"}, NICHE, "cap")
        self.assertEqual((ok, via, pid), (True, "inbox", "inbox1"))

    def test_without_token_it_uses_the_inbox(self):
        with mock.patch.object(buffer, "enabled", lambda: False), \
             mock.patch.object(autopilot, "upload_tiktok", lambda v, m, n: "inbox1"):
            ok, via, pid = autopilot.publish_tiktok("/tmp/v.mp4", {"title": "T"}, NICHE, "cap")
        self.assertEqual(via, "inbox")

    def test_captions_file_skips_posts_buffer_already_captioned(self):
        import tempfile as tf
        with tf.TemporaryDirectory() as tmp:
            state = {"uploads": [
                {"ts": "t1", "niche": "codeaz", "tiktok": True, "tiktok_via": "buffer",
                 "tiktok_caption": "already published"},
                {"ts": "t2", "niche": "codeaz", "tiktok": True, "tiktok_via": "inbox",
                 "tiktok_caption": "needs pasting"},
            ]}
            with mock.patch.object(autopilot, "ROOT", Path(tmp)):
                autopilot.write_pending_captions(state)
                text = (Path(tmp) / "CAPTIONS.md").read_text()
        self.assertIn("needs pasting", text)
        self.assertNotIn("already published", text)


class RetryTest(unittest.TestCase):
    def test_transient_failure_is_retried_within_the_run(self):
        calls = []

        def run_niche(niche, state):
            calls.append(1)
            if len(calls) < 3:
                raise RuntimeError("NIM read timeout")

        with mock.patch.object(autopilot, "run_niche", run_niche), \
             mock.patch.object(autopilot.time, "sleep"):
            autopilot.run_niche_with_retries(NICHE, {}, attempts=3)
        self.assertEqual(len(calls), 3)

    def test_persistent_failure_still_raises(self):
        with mock.patch.object(autopilot, "run_niche",
                               mock.Mock(side_effect=RuntimeError("still broken"))), \
             mock.patch.object(autopilot.time, "sleep"):
            with self.assertRaises(RuntimeError):
                autopilot.run_niche_with_retries(NICHE, {}, attempts=2)


class RunNicheTest(unittest.TestCase):
    """The full loop, with MPT and both upload targets stubbed."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.patches = [
            mock.patch.object(autopilot, "ROOT", root),
            mock.patch.object(autopilot, "STATE_FILE", root / "posted.json"),
            mock.patch.object(autopilot, "OUT_DIR", root / "out"),
            mock.patch.object(autopilot, "pick_topic",
                              lambda n, u, ids=(): ("Race conditions, two waiters",
                                                   {"id": "reddit:x", "title": "why?", "url": "u"})),
            mock.patch.object(autopilot, "generate_script", lambda t, n, q=None, **kw: SCRIPT),
            mock.patch.object(autopilot, "generate_terms", lambda t, s, n: "waiter,table"),
            mock.patch.object(autopilot, "render_with_fallback",
                              lambda t, n, s, x: str(root / "video.mp4")),
            # render_video now returns (path, archetype); the stubbed
            # render_with_fallback above is called via that wrapper.
            mock.patch.object(autopilot, "render_video",
                              lambda t, n, s, **kw:
                              (str(root / "video.mp4"),
                               kw.get("force_archetype") or "QuestionAnswer")),
            # the stub file is not a real video; the render check has its own tests
            mock.patch.object(autopilot, "check_rendered_video", lambda p, s: 60.0),
            mock.patch.object(autopilot, "make_metadata",
                              lambda t, n, question=None, repo=None:
                              {"title": "Race Conditions", "description": "desc",
                               "hashtags": ["#test", "#tags"]}),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)
        (root / "video.mp4").write_bytes(b"x")
        self.root = root

    def test_uploads_and_state(self):
        uploads = {}
        with mock.patch.object(autopilot, "DRY_RUN", False), \
             mock.patch.object(autopilot, "upload_youtube",
                               lambda v, m, n: (uploads.__setitem__("yt", True), "yt123")[1]), \
             mock.patch.object(autopilot, "upload_tiktok",
                               lambda v, m, n: (uploads.__setitem__("tt", True), "pub1")[1]), \
             mock.patch.object(buffer, "enabled", lambda: False):
            state = {"topics": {}, "uploads": []}
            autopilot.run_niche(NICHE, state)

        self.assertEqual(uploads, {"yt": True, "tt": True})
        entry = state["uploads"][-1]
        self.assertEqual(entry["youtube"], "yt123")
        self.assertTrue(entry["tiktok"])
        # Caption should carry whatever hashtags make_metadata returned for THIS
        # video (dynamic per-topic tags); niche-static #programming is now only
        # a fallback and not exercised by this path.
        self.assertIn("#test", entry["tiktok_caption"])
        self.assertTrue((self.root / "CAPTIONS.md").exists())
        self.assertIn("Race Conditions", (self.root / "CAPTIONS.md").read_text())

    def test_dry_run_uploads_nothing_and_keeps_state_clean(self):
        def fail(*a, **k):
            raise AssertionError("DRY_RUN must not upload")

        with mock.patch.object(autopilot, "DRY_RUN", True), \
             mock.patch.object(autopilot, "upload_youtube", fail), \
             mock.patch.object(buffer, "publish", fail), \
             mock.patch.object(autopilot, "upload_tiktok", fail):
            state = {"topics": {}, "uploads": []}
            autopilot.run_niche(NICHE, state)

        self.assertEqual(state["uploads"], [], "a dry run must not record an upload")
        self.assertFalse((self.root / "posted.json").exists(),
                         "a dry run must not write state the next real run reads")
        out = list((self.root / "out").glob("*.mp4"))
        self.assertEqual(len(out), 1, "the video should be left in ./out for review")
        sidecar = out[0].with_suffix(".txt").read_text()
        self.assertIn("tiktok caption:", sidecar)
        self.assertIn("script:", sidecar)

    def test_star_rising_run_records_the_repo_and_flips_the_mode(self):
        niche = {**NICHE, "star_rising": {"enabled": True, "every_other_run": True}}
        picked = repo("acme/thing")
        with mock.patch.object(autopilot, "DRY_RUN", False), \
             mock.patch.object(repos, "pick",
                               lambda n, covered=(): ("The self-hosted invoicing app", picked)), \
             mock.patch.object(autopilot, "upload_youtube", lambda v, m, n: "yt123"), \
             mock.patch.object(autopilot, "upload_tiktok", lambda v, m, n: "pub1"), \
             mock.patch.object(buffer, "enabled", lambda: False):
            state = {"topics": {}, "uploads": []}
            autopilot.run_niche(niche, state)

        entry = state["uploads"][-1]
        self.assertEqual(entry["mode"], "star_rising")
        self.assertEqual(entry["repo"], "acme/thing")
        self.assertEqual(entry["archetype"], "StarRising")
        self.assertIsNone(entry["question_id"], "a repo episode answers no harvested question")
        self.assertIn("acme/thing", state["repos"]["codeaz"])
        # the next run must go back to the question pipeline
        self.assertFalse(autopilot.star_rising_turn(niche, state))

    def test_a_dry_run_does_not_spend_the_repo_a_real_run_would_cover(self):
        niche = {**NICHE, "star_rising": {"enabled": True, "every_other_run": True}}
        picked = repo("acme/thing")
        with mock.patch.object(autopilot, "DRY_RUN", True), \
             mock.patch.object(repos, "pick",
                               lambda n, covered=(): ("The self-hosted invoicing app", picked)), \
             mock.patch.object(autopilot, "upload_youtube",
                               mock.Mock(side_effect=AssertionError("no uploads"))):
            state = {"topics": {}, "uploads": []}
            autopilot.run_niche(niche, state)

        self.assertFalse((self.root / "posted.json").exists())
        # in-memory only, so a second video in the same run still picks a new repo
        self.assertIn("acme/thing", state["repos"]["codeaz"])

    def test_a_dead_github_falls_back_to_the_question_pipeline(self):
        """A quiet week on GitHub costs a topic, never a run."""
        niche = {**NICHE, "star_rising": {"enabled": True, "every_other_run": True}}
        with mock.patch.object(autopilot, "DRY_RUN", False), \
             mock.patch.object(repos, "pick",
                               mock.Mock(side_effect=RuntimeError("no fresh repos"))), \
             mock.patch.object(autopilot, "upload_youtube", lambda v, m, n: "yt123"), \
             mock.patch.object(autopilot, "upload_tiktok", lambda v, m, n: "pub1"), \
             mock.patch.object(buffer, "enabled", lambda: False):
            state = {"topics": {}, "uploads": []}
            autopilot.run_niche(niche, state)

        entry = state["uploads"][-1]
        self.assertEqual(entry["mode"], "question")
        self.assertIsNone(entry["repo"])
        self.assertEqual(entry["question_id"], "reddit:x")

    def test_a_paused_question_pipeline_ships_nothing_rather_than_a_question_video(self):
        """With questions paused, a day where GitHub yields nothing must publish
        nothing -- not quietly fall back to a format the channel has stopped."""
        niche = {**NICHE, "star_rising": {"enabled": True, "every_other_run": False,
                                          "fallback_to_questions": False}}
        with mock.patch.object(autopilot, "DRY_RUN", False), \
             mock.patch.object(repos, "pick",
                               mock.Mock(side_effect=RuntimeError("no fresh repos"))), \
             mock.patch.object(autopilot, "upload_youtube",
                               mock.Mock(side_effect=AssertionError("must not publish"))):
            state = {"topics": {}, "uploads": []}
            autopilot.run_niche(niche, state)
        self.assertEqual(state["uploads"], [])

    def test_the_fallback_still_works_for_niches_that_want_it(self):
        niche = {**NICHE, "star_rising": {"enabled": True, "every_other_run": False,
                                          "fallback_to_questions": True}}
        with mock.patch.object(autopilot, "DRY_RUN", False), \
             mock.patch.object(repos, "pick",
                               mock.Mock(side_effect=RuntimeError("no fresh repos"))), \
             mock.patch.object(autopilot, "upload_youtube", lambda v, m, n: "yt123"), \
             mock.patch.object(autopilot, "upload_tiktok", lambda v, m, n: "pub1"), \
             mock.patch.object(buffer, "enabled", lambda: False):
            state = {"topics": {}, "uploads": []}
            autopilot.run_niche(niche, state)
        self.assertEqual(state["uploads"][-1]["mode"], "question")

    def test_one_failing_niche_does_not_stop_the_others(self):
        calls = []

        def run_niche(niche, state):
            calls.append(niche["id"])
            if niche["id"] == "bad":
                raise RuntimeError("boom")

        niches = {"niches": [{**NICHE, "id": "bad"}, {**NICHE, "id": "good"}]}
        (self.root / "niches.json").write_text(json.dumps(niches))
        with mock.patch.object(autopilot, "run_niche", run_niche), \
             mock.patch.object(autopilot, "load_state", lambda: {"topics": {}, "uploads": []}), \
             mock.patch.object(autopilot.time, "sleep"):
            with self.assertRaises(SystemExit) as ctx:
                autopilot.main()
        # the bad niche is retried, then the good one still runs
        self.assertEqual(calls, ["bad"] * autopilot.RUN_ATTEMPTS + ["good"],
                         "a failing niche must not stop the rest")
        self.assertIn("bad", str(ctx.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
