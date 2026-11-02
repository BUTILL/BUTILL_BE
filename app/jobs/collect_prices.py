import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from app.database.ingredient_prices import open_price_writer
from app.database.kamis import open_kamis_client
from app.errors import DomainError
from app.services.price_collection import KST, run_collection
from app.services.price_items import PRICE_ITEMS


def main() -> int:
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    try:
        with open_kamis_client() as client, open_price_writer() as repo:
            run = run_collection(client, repo, PRICE_ITEMS, datetime.now(KST).date())
    except DomainError as exc:
        print(f"가격 수집 실패: {exc.code}", file=sys.stderr)
        return 1
    print(f"가격 수집 {run.status}: 성공 {run.success_count}, 실패 {run.failure_count}, 저장 {run.saved_count}건")
    for result in run.item_results:
        if result.status != "success":
            print(f"- {result.key}: {result.status} {result.error_code or ''}".rstrip())
    return 1 if run.status == "failed" else 0


if __name__ == "__main__":
    sys.exit(main())
