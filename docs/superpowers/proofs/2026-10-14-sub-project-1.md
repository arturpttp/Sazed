# Discrimination proofs — sub-project 1

Each entry: the property, the mutation (a bug a person would write), the failing output, reverted.

## Architecture guard
Mutation: `import sazed.runtime` in `sazed/core/__init__.py`.
```
>       assert violations == []
E       AssertionError: assert ['__init__.py: sazed.runtime'] == []
FAILED tests/test_architecture.py::test_package_imports_only_what_it_may[core]
1 failed, 8 passed in 0.07s
```
Mutation: `datetime.now()` in `sazed/core/__init__.py`.
```
>       assert violations == []
E       AssertionError: assert ['__init__.py:4 .now'] == []
FAILED tests/test_architecture.py::test_pure_packages_do_not_touch_clock_env_or_io[core]
1 failed, 8 passed in 0.07s
```
