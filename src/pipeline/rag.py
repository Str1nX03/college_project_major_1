import chromadb
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import OllamaEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter

class RAGPipeline:
    """
    A class to handle the Retrieval-Augmented Generation (RAG) pipeline.
    It manages creating a vector store from documents and providing a retriever.
    """
    def __init__(self, ollama_embedding_model: str = "nomic-embed-text"):
        """
        Initializes the RAGPipeline.

        Args:
            ollama_embedding_model (str): The name of the Ollama embedding model to use.
        """
        print("Initializing RAG Pipeline...")
        self.vector_store = None
        self.retriever = None
        self.text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
        
        # Use a persistent ChromaDB client
        client = chromadb.Client()
        
        self.vector_store = Chroma(
            client=client,
            collection_name="ai_tutor_rag",
            embedding_function=OllamaEmbeddings(model=ollama_embedding_model, show_progress=True)
        )
        print("RAG Pipeline Initialized.")

    def add_documents_to_vectorstore(self, documents: list):
        """
        Splits documents, creates embeddings, and adds them to the vector store.

        Args:
            documents (list): A list of documents (text content) to be added.
        """
        print(f"Adding {len(documents)} documents to the vector store...")
        texts = self.text_splitter.split_documents(documents)
        self.vector_store.add_documents(texts)
        self.retriever = self.vector_store.as_retriever()
        print("Documents added and retriever is ready.")

    def get_retriever(self):
        """
        Returns the retriever object from the vector store.

        Returns:
            A LangChain retriever instance.
        """
        if self.retriever is None:
            print("Retriever not yet initialized. Please add documents first.")
        return self.retriever
