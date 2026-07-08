from app.api.inventory import normalize_transaction_type


def test_stock_in_restocks_are_mapped_to_return_for_db_compatibility():
    assert normalize_transaction_type("restock", "stock_in") == "Return"


def test_stock_out_issues_remain_issue():
    assert normalize_transaction_type("Issue", "stock_out") == "Issue"
