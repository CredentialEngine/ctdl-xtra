# Every check a wave gate runs. `make check` = Python tests + lint + web typecheck/tests/build.
.PHONY: check py-test py-lint web-test web-build slow
check: py-lint py-test web-test web-build

py-test:
	uv run pytest -q

py-lint:
	uv run ruff check src tests bench

web-test:
	cd web && npm run typecheck && npm test

web-build:
	cd web && npm run build

slow:  # end-to-end on the local mirror (needs ~/review-ui-v3-data)
	uv run pytest -q -m slow
