def compact_match_payload(match_state):
    return match_state.to_dict(include_events=False)


def detailed_match_payload(match_state):
    return match_state.to_dict(include_events=True)

