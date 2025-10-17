import os
import json
from typing import TypedDict, Annotated, List
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_ollama.chat_models import ChatOllama
from langchain_community.tools.tavily_search import TavilySearchResults
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from src.pipeline.rag import RAGPipeline

# Set Tavily API key for web search
os.environ["TAVILY_API_KEY"] = "YOUR_TAVILY_API_KEY" # Replace with your Tavily API key

class AgentState(TypedDict):
    """
    Represents the state of our agent.
    
    Attributes:
        topic (str): The subject or topic the user wants to learn.
        lesson_plan (List[str]): A structured list of lessons.
        current_lesson_index (int): The index of the current lesson in the plan.
        messages (List[BaseMessage]): The history of messages in the conversation.
        user_response (str): The latest response from the user.
    """
    topic: str
    lesson_plan: List[str]
    current_lesson_index: int
    messages: Annotated[List[BaseMessage], lambda x, y: x + y]
    user_response: str

class LessonPlan(BaseModel):
    """Data model for a lesson plan."""
    lessons: List[str] = Field(description="A detailed list of lessons to teach the user about the topic.")

class TutorAgent:
    """
    The main class for the AI Tutoring Agent.
    It builds and runs the LangGraph-based agent.
    """
    def __init__(self, ollama_model: str = "deepseek-v3.1:671b-cloud"):
        """
        Initializes the TutorAgent.

        Args:
            ollama_model (str): The name of the Ollama model to use for generation.
        """
        print("Initializing Tutor Agent...")
        self.llm = ChatOllama(model=ollama_model, temperature=0)
        self.rag_pipeline = RAGPipeline()
        self.tools = [TavilySearchResults(max_results=5)]
        self.tool_node = ToolNode(self.tools)
        self.graph = self._build_graph()
        print("Tutor Agent Initialized.")

    def _build_graph(self):
        """
        Builds the computational graph for the agent's workflow.
        """
        print("Building agent graph...")
        # Define the structured LLM for generating the lesson plan
        structured_llm = self.llm.with_structured_output(LessonPlan)

        # Graph Definition
        workflow = StateGraph(AgentState)

        # 1. Node: Plan Lessons
        def plan_lessons_node(state: AgentState):
            print("---PLANNING LESSONS---")
            messages = [
                SystemMessage(
                    content=(
                        "You are an expert curriculum designer. Your task is to create a "
                        "comprehensive and easy-to-follow lesson plan for a given topic. "
                        "The plan should break down the topic into smaller, manageable lessons."
                    )
                ),
                HumanMessage(content=f"Create a lesson plan for the topic: {state['topic']}")
            ]
            response = structured_llm.invoke(messages)
            return {"lesson_plan": response.lessons, "current_lesson_index": 0}

        # 2. Node: Search for Content
        def search_content_node(state: AgentState):
            print("---SEARCHING FOR CONTENT---")
            topic = state["topic"]
            # This simulates a tool call to Tavily Search
            search_results = self.tools[0].invoke({"query": f"In-depth educational content on {topic}"})
            
            # For simplicity, we'll process the search results here.
            # In a more complex agent, this could be part of the tool logic.
            documents_for_rag = [result['content'] for result in search_results]
            
            # This is a bit of a workaround to get documents into RAG
            # In a real scenario, you might have a dedicated state for this
            self.rag_pipeline.add_documents_to_vectorstore(documents_for_rag)
            
            return {}


        # 3. Node: Deliver Lesson
        def deliver_lesson_node(state: AgentState):
            print("---DELIVERING LESSON---")
            plan = state["lesson_plan"]
            idx = state["current_lesson_index"]
            current_lesson_topic = plan[idx]
            
            retriever = self.rag_pipeline.get_retriever()
            retrieved_docs = retriever.invoke(current_lesson_topic)
            context = "\n\n".join([doc.page_content for doc in retrieved_docs])

            prompt = (
                f"You are an AI Tutor. Explain the following lesson to me in a simple and "
                f"easy-to-understand way. Use the provided context to ensure accuracy.\n\n"
                f"Lesson: {current_lesson_topic}\n\n"
                f"Context from research:\n{context}\n\n"
                f"Your Explanation:"
            )
            
            response = self.llm.invoke(prompt)
            
            next_lesson_preview = ""
            if idx + 1 < len(plan):
                next_lesson_preview = f"\n\n*Next up, we'll be looking at: {plan[idx+1]}*"

            message_content = response + next_lesson_preview
            return {"messages": [HumanMessage(content=message_content)]}

        # 4. Node: Simplify Lesson
        def simplify_lesson_node(state: AgentState):
            print("---SIMPLIFYING LESSON---")
            # Get the last lesson delivered by the agent
            last_lesson = state["messages"][-1].content.split("\n\n*Next up")[0]
            
            prompt = (
                f"You are an AI Tutor. Please re-explain the following lesson in an even "
                f"simpler way, using analogies and simple examples if possible.\n\n"
                f"Lesson to simplify:\n{last_lesson}\n\n"
                f"Your Simplified Explanation:"
            )
            response = self.llm.invoke(prompt)
            
            # Re-add the "next lesson" preview
            plan = state["lesson_plan"]
            idx = state["current_lesson_index"]
            next_lesson_preview = ""
            if idx + 1 < len(plan):
                next_lesson_preview = f"\n\n*Next up, we'll be looking at: {plan[idx+1]}*"

            message_content = response + next_lesson_preview
            return {"messages": [HumanMessage(content=message_content)]}


        # Conditional Edge Logic
        def should_continue_or_end(state: AgentState):
            user_resp = state.get("user_response", "").lower()
            
            if "next" in user_resp:
                next_idx = state["current_lesson_index"] + 1
                if next_idx < len(state["lesson_plan"]):
                    print("---DECISION: NEXT LESSON---")
                    # Update state for the next lesson
                    state["current_lesson_index"] = next_idx
                    return "deliver_lesson"
                else:
                    print("---DECISION: END OF PLAN---")
                    return END
            elif "replay" in user_resp:
                print("---DECISION: REPLAY LESSON---")
                return "simplify_lesson"
            else:
                # This case is for the initial run after planning
                return "deliver_lesson"


        # Add nodes to the graph
        workflow.add_node("plan_lessons", plan_lessons_node)
        workflow.add_node("search_content", search_content_node)
        workflow.add_node("deliver_lesson", deliver_lesson_node)
        workflow.add_node("simplify_lesson", simplify_lesson_node)

        # Set entry point
        workflow.set_entry_point("plan_lessons")
        
        # Add edges
        workflow.add_edge("plan_lessons", "search_content")
        workflow.add_edge("search_content", "deliver_lesson")
        workflow.add_edge("simplify_lesson", "deliver_lesson") # After simplifying, it loops back to deliver the simplified content
        
        # Add conditional edge
        workflow.add_conditional_edges(
            "deliver_lesson",
            should_continue_or_end,
            {
                "deliver_lesson": "deliver_lesson",
                "simplify_lesson": "simplify_lesson",
                 END: END
            }
        )

        # Compile the graph
        print("Agent graph built.")
        return workflow.compile()

    def run(self, topic: str, user_response: str = None):
        """
        Runs the agent for a given topic and optional user response.

        Args:
            topic (str): The initial topic to learn.
            user_response (str, optional): The user's response to a previous lesson.

        Returns:
            A dictionary containing the agent's state.
        """
        initial_state = AgentState(
            topic=topic, 
            messages=[], 
            user_response=user_response,
            lesson_plan=[],
            current_lesson_index=0
        )
        # The stream method allows us to step through the graph
        # For a web app, we might run it step-by-step
        final_state = self.graph.invoke(initial_state)
        return final_state