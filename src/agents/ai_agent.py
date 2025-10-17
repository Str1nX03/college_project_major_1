import os
import json
from typing import TypedDict, Annotated, List
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage
from pydantic import BaseModel, Field, conlist
from langchain_ollama.chat_models import ChatOllama
from langchain_community.tools.tavily_search import TavilySearchResults
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from src.pipeline.rag import RAGPipeline
from dotenv import load_dotenv
load_dotenv()

# Tavily API key should be set in Replit Secrets as TAVILY_API_KEY

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

# NEW DETAILED MODELS
class LessonActivity(BaseModel):
    """Data model for a single activity within a lesson."""
    activity_name: str = Field(description="The title of the lesson activity.")
    description: str = Field(description="A brief description of what the activity entails.")

class DetailedLessonPlan(BaseModel):
    """Data model for a detailed lesson plan."""
    learning_objectives: List[str] = Field(description="A list of what the user will learn.")
    lesson_activities: List[LessonActivity] = Field(description="A detailed list of lessons and activities to teach the user about the topic.")

# NEW, MORE DETAILED MODELS
class Activity(BaseModel):
    """A single activity within a session."""
    activity: str = Field(description="The title of the activity.")
    description: str = Field(description="A brief description of what the activity entails.")

class Session(BaseModel):
    """A single teaching session in the lesson plan."""
    session_number: int
    title: str
    activities: List[str]

class FullLessonPlan(BaseModel):
    """The complete, detailed lesson plan structure."""
    learning_objectives: List[str]
    sessions: List[Session]

class LessonPlanWrapper(BaseModel):
    """A wrapper to match the LLM's top-level 'lesson_plan' key."""
    lesson_plan: FullLessonPlan

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
        structured_llm = self.llm.with_structured_output(LessonPlanWrapper)

        # --- NODE DEFINITIONS (Unchanged) ---
        # 1. Node: Plan Lessons
        def plan_lessons_node(state: AgentState):
            print("---PLANNING LESSONS---")
            messages = [
                SystemMessage(
                    content=(
                        "You are an expert curriculum designer. Create a comprehensive, session-based "
                        "lesson plan for the given topic. The plan should include learning objectives "
                        "and a list of sessions, each with its own set of activities. "
                        "Respond with a single JSON object wrapped in a 'lesson_plan' key."
                    )
                ),
                HumanMessage(content=f"Create a detailed lesson plan for the topic: {state['topic']}")
            ]
            response = structured_llm.invoke(messages)
            full_plan = response.lesson_plan
            all_activities = [activity for session in full_plan.sessions for activity in session.activities]
            return {"lesson_plan": all_activities, "current_lesson_index": 0}

        # 2. Node: Search for Content
        def search_content_node(state: AgentState):
            print("---SEARCHING FOR CONTENT---")
            topic = state["topic"]
            search_results = self.tools[0].invoke({"query": f"In-depth educational content on {topic}"})
            documents_for_rag = [result['content'] for result in search_results]
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
                next_lesson_preview = f"\n\n*Next up: {plan[idx+1]}*"
            message_content = response.content + next_lesson_preview
            return {"messages": [HumanMessage(content=message_content)]}

        # 4. Node: Simplify Lesson
        def simplify_lesson_node(state: AgentState):
            print("---SIMPLIFYING LESSON---")
            last_lesson = state["messages"][-1].content.split("\n\n*Next up")[0]
            prompt = (
                f"You are an AI Tutor. Please re-explain the following lesson in an even "
                f"simpler way, using analogies and simple examples if possible.\n\n"
                f"Lesson to simplify:\n{last_lesson}\n\n"
                f"Your Simplified Explanation:"
            )
            response = self.llm.invoke(prompt)
            plan = state["lesson_plan"]
            idx = state["current_lesson_index"]
            next_lesson_preview = ""
            if idx + 1 < len(plan):
                next_lesson_preview = f"\n\n*Next up: {plan[idx+1]}*"
            message_content = response.content + next_lesson_preview
            return {"messages": [HumanMessage(content=message_content)]}

        # --- NEW GRAPH STRUCTURE ---

        # 1. NEW Main Router Logic
        def main_router(state: AgentState):
            """
            This node acts as the main entry point and router for the graph.
            It decides whether to create a new lesson plan or process user input.
            """
            print("---MAIN ROUTER---")
            # If there is no lesson plan, we need to create one.
            if not state.get("lesson_plan"):
                print("---ROUTE: No plan found. Routing to 'plan_lessons'.")
                return "plan_lessons"
            
            # If a plan exists, process the user's response.
            else:
                print("---ROUTE: Plan found. Processing user response.")
                user_resp = state.get("user_response", "").lower()
                
                if "next" in user_resp:
                    next_idx = state["current_lesson_index"] + 1
                    if next_idx < len(state["lesson_plan"]):
                        print("---DECISION: Advance to next lesson.")
                        # Update the index in the state for the next node to use
                        state["current_lesson_index"] = next_idx
                        return "deliver_lesson"
                    else:
                        print("---DECISION: End of lesson plan.")
                        return END
                
                elif "replay" in user_resp:
                    print("---DECISION: Simplify current lesson.")
                    return "simplify_lesson"
                
                else:
                    # If the input is not recognized, just end the turn.
                    # A more complex agent could route to a clarification node here.
                    print("---DECISION: Unrecognized input. Ending turn.")
                    return END

        # 2. Define the graph workflow
        workflow = StateGraph(AgentState)

        # Add all the nodes
        workflow.add_node("main_router", main_router)
        workflow.add_node("plan_lessons", plan_lessons_node)
        workflow.add_node("search_content", search_content_node)
        workflow.add_node("deliver_lesson", deliver_lesson_node)
        workflow.add_node("simplify_lesson", simplify_lesson_node)

        # 3. Set the new router as the entry point
        workflow.set_entry_point("main_router")

        # 4. Add edges
        
        # The main router decides where to go first
        workflow.add_conditional_edges(
            "main_router",
            main_router, # The router function itself returns the name of the next node
            {
                "plan_lessons": "plan_lessons",
                "deliver_lesson": "deliver_lesson",
                "simplify_lesson": "simplify_lesson",
                END: END
            }
        )
        
        # The flow for creating a new plan
        workflow.add_edge("plan_lessons", "search_content")
        workflow.add_edge("search_content", "deliver_lesson")

        # All action nodes now lead directly to the end of the graph for this turn
        workflow.add_edge("deliver_lesson", END)
        workflow.add_edge("simplify_lesson", END)

        # 5. Compile the graph
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