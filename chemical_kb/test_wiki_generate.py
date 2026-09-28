from core.rag import RAGSystem
from core.wiki_generator import WikiGenerator



print("="*60)
print("初始化RAG")
print("="*60)


rag = RAGSystem()



print("="*60)
print("初始化Wiki Generator")
print("="*60)


generator = WikiGenerator(
    rag_system=rag
)



result = generator.generate(
    "液氯"
)



print(
    result["quality"]
)