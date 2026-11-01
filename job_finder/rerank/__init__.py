"""LLM rerank support: build a review packet for Claude, then merge its verdicts.

Python never calls a model. ``packet`` prepares what the orchestrating Claude session
hands to reviewer subagents, and ``merge`` validates and combines what they return.
"""
