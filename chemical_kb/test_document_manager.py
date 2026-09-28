from core.document_manager import DocumentManager


manager = DocumentManager()


manager.add_document(
    {
        "doc_id":
            "TEST_001",

        "title":
            "测试危险化学品标准",

        "document_type":
            "标准",

        "code":
            "TEST-001",

        "chunks":
            10
    }
)


print(
    manager.get_all_documents()
)


print(
    manager.get_statistics()
)