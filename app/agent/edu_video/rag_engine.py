from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document

class RAGEngine:
    def __init__(self, units: list, *, collection_name: str = "edu_rag", persist_directory: str | None = None):
        self.documents = [
            Document(
                page_content=u['content'],
                metadata={
                    "id": u.get('id'),
                    "source": u.get('source'),
                    "page": u.get('page')
                }
            )
            for u in units
        ]
        self.embeddings = OpenAIEmbeddings()
        self.vectorstore = Chroma.from_documents(
            documents=self.documents, 
            embedding=self.embeddings,
            collection_name=collection_name,
            persist_directory=persist_directory
        )
        self.retriever = self.vectorstore.as_retriever()
        
    def get_context(self, query: str):
        docs = self.retriever.invoke(query)
        return "\n\n".join([d.page_content for d in docs])
    
    def get_detailed_context(self, query: str):
        # 관련 문서 3~4개를 가져옵니다.
        docs = self.retriever.invoke(query)
        context_list = []
        for d in docs:
            source = d.metadata.get('source', '알 수 없는 파일')
            page = d.metadata.get('page', '?')
            content = d.page_content
            context_list.append({
                "source": source,
                "page": page,
                "content": content
            })
        return context_list