"""Stratified train/validation/test split - the 3-way generalization of
training/preprocessing/build_training_set.py:stratified_split (which stays
2-way, for the existing v0/v1/v1.1 pipeline). Test is held out and must
never be touched by tuning - this module doesn't enforce that at runtime
(nothing can), but keeping it in its own file that nothing else reads by
default is the structural safeguard: only evaluation reporting should ever
open test.jsonl.
"""

import random
from collections import defaultdict
from dataclasses import dataclass

from training.pipeline.schema import RawExample

DEFAULT_TRAIN_FRACTION = 0.90
DEFAULT_VAL_FRACTION = 0.05
DEFAULT_TEST_FRACTION = 0.05
MIN_VAL_PER_CLASS = 2
MIN_TEST_PER_CLASS = 2
MIN_CLASS_SIZE_FOR_SPLIT = 6  # needs room for >=2 val + >=2 test + >=1 train more than the union split


@dataclass
class SplitResult:
    train: list[RawExample]
    val: list[RawExample]
    test: list[RawExample]


def stratified_three_way_split(
    examples: list[RawExample],
    *,
    val_fraction: float = DEFAULT_VAL_FRACTION,
    test_fraction: float = DEFAULT_TEST_FRACTION,
    seed: int = 42,
    stratify_by: str = "intent",
    min_val_per_class: int = MIN_VAL_PER_CLASS,
    min_test_per_class: int = MIN_TEST_PER_CLASS,
    min_class_size_for_split: int = MIN_CLASS_SIZE_FOR_SPLIT,
) -> SplitResult:
    rng = random.Random(seed)
    by_class: dict[str, list[RawExample]] = defaultdict(list)
    for ex in examples:
        by_class[getattr(ex, stratify_by)].append(ex)

    train: list[RawExample] = []
    val: list[RawExample] = []
    test: list[RawExample] = []

    for key in sorted(by_class):
        items = by_class[key][:]
        rng.shuffle(items)
        count = len(items)
        if count < min_class_size_for_split:
            train.extend(items)
            continue

        n_val = max(min_val_per_class, round(count * val_fraction))
        n_test = max(min_test_per_class, round(count * test_fraction))
        # Never let val+test consume the whole class - leave at least 1 for train.
        while n_val + n_test >= count:
            if n_val >= n_test:
                n_val -= 1
            else:
                n_test -= 1

        val.extend(items[:n_val])
        test.extend(items[n_val:n_val + n_test])
        train.extend(items[n_val + n_test:])

    for bucket in (train, val, test):
        rng.shuffle(bucket)

    return SplitResult(train=train, val=val, test=test)
