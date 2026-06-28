"""TDD for the reliability-weighted K-agreement consolidator (the named mechanism)."""
from veche.types import Observation
from veche.consolidator import consolidate


def test_weighted_k_agreement_overrules_the_wrong_agent():
    # The demo hero: 4 agents land on the SAME screen after clicking Submit on the lab-entry
    # screen. Agent a3 misreads a low-contrast 'critical' flag and reports the happy-path screen.
    obs = [
        Observation("a1", "lab_entry", "click:Submit", "critical_confirm"),
        Observation("a2", "lab_entry", "click:Submit", "critical_confirm"),
        Observation("a3", "lab_entry", "click:Submit", "happy_confirm"),   # the misread
        Observation("a4", "lab_entry", "click:Submit", "critical_confirm"),
    ]
    res = consolidate(obs, k=2)
    e = res.edge("lab_entry", "click:Submit")

    assert e is not None
    assert e.to_node == "critical_confirm"     # consensus picks the truth
    assert e.committed is True                  # 3 distinct agents >= k=2
    assert e.confirmations == 3
    assert e.is_conflict is True
    assert "happy_confirm" in e.quarantined     # loser kept visible, not deleted

    # the misreading agent's reliability drops below the agents who were right
    assert res.reliability["a3"] < res.reliability["a1"]


def test_no_conflict_clean_transition_commits():
    obs = [
        Observation("a1", "home", "click:Patients", "patient_list"),
        Observation("a2", "home", "click:Patients", "patient_list"),
    ]
    res = consolidate(obs, k=2)
    e = res.edge("home", "click:Patients")
    assert e.to_node == "patient_list"
    assert e.committed is True
    assert e.is_conflict is False
    assert e.quarantined == []


def test_below_k_is_not_committed():
    obs = [Observation("a1", "home", "click:Billing", "billing")]
    res = consolidate(obs, k=2)
    e = res.edge("home", "click:Billing")
    assert e.to_node == "billing"
    assert e.committed is False        # only 1 agent, below k=2
