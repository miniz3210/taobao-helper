"""
AI Query Assistant Module
Provides natural language querying of purchase history using LLM + SQL
"""
import os
import json
from typing import List, Dict, Optional
from datetime import datetime
from sqlalchemy import select, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order

try:
    from litellm import acompletion
    LITELLM_AVAILABLE = True
except ImportError:
    LITELLM_AVAILABLE = False


class AIQueryAssistant:
    """AI-powered natural language query interface for order history"""
    
    def __init__(self):
        self.openai_key = os.getenv('OPENAI_API_KEY')
        self.gemini_key = os.getenv('GEMINI_API_KEY')
        
        # Determine which model to use
        if self.gemini_key:
            self.model = "gemini/gemini-pro"
            os.environ['GEMINI_API_KEY'] = self.gemini_key
        elif self.openai_key:
            self.model = "gpt-3.5-turbo"
            os.environ['OPENAI_API_KEY'] = self.openai_key
        else:
            self.model = None
    
    async def query(
        self, 
        user_query: str, 
        session: AsyncSession
    ) -> Dict[str, any]:
        """
        Process natural language query and return results with images
        """
        # Extract search parameters from query using LLM
        search_params = await self._extract_search_params(user_query)
        
        # Search database
        orders = await self._search_orders(session, search_params)
        
        # Generate natural language response
        response_text = await self._generate_response(user_query, orders, search_params)
        
        return {
            'query': user_query,
            'response': response_text,
            'orders': [order.to_dict() for order in orders],
            'count': len(orders)
        }
    
    async def _extract_search_params(self, user_query: str) -> Dict:
        """
        Use LLM to extract search parameters from natural language query
        """
        if not LITELLM_AVAILABLE or not self.model:
            # Fallback: basic keyword extraction
            return self._basic_keyword_extraction(user_query)
        
        system_prompt = """You are a query parameter extractor for an e-commerce order database.
Extract search parameters from user queries and return them as JSON.

Available parameters:
- keywords: list of product keywords to search for
- date_from: start date (YYYY-MM-DD)
- date_to: end date (YYYY-MM-DD)
- min_price: minimum price in RMB
- max_price: maximum price in RMB
- status: order status (pending_shipment, in_transit, received)

Examples:
Query: "What toothbrush brands did I buy in 2025?"
Output: {"keywords": ["toothbrush"], "date_from": "2025-01-01", "date_to": "2025-12-31"}

Query: "Show me items over 100 RMB that haven't arrived"
Output: {"min_price": 100, "status": "in_transit"}

Return only the JSON object, no explanations."""

        try:
            response = await acompletion(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_query}
                ],
                temperature=0.1
            )
            
            content = response.choices[0].message.content
            
            # Extract JSON from response
            if '{' in content and '}' in content:
                json_start = content.find('{')
                json_end = content.rfind('}') + 1
                json_str = content[json_start:json_end]
                return json.loads(json_str)
            
            return {}
            
        except Exception as e:
            print(f"Error extracting search params with LLM: {e}")
            return self._basic_keyword_extraction(user_query)
    
    def _basic_keyword_extraction(self, query: str) -> Dict:
        """Basic keyword extraction without LLM"""
        keywords = []
        
        # Extract words that might be product names (nouns)
        words = query.lower().split()
        
        # Remove common question words
        stop_words = {'what', 'when', 'where', 'how', 'did', 'do', 'i', 'buy', 'bought', 
                     'purchase', 'purchased', 'order', 'ordered', 'show', 'find', 'get'}
        
        keywords = [w for w in words if w not in stop_words and len(w) > 2]
        
        return {'keywords': keywords[:5]}  # Limit to 5 keywords
    
    async def _search_orders(
        self, 
        session: AsyncSession, 
        search_params: Dict
    ) -> List[Order]:
        """
        Search orders based on extracted parameters
        """
        query = select(Order)
        conditions = []
        
        # Keyword search
        if search_params.get('keywords'):
            keyword_conditions = []
            for keyword in search_params['keywords']:
                keyword_conditions.append(Order.item_title.ilike(f'%{keyword}%'))
                keyword_conditions.append(Order.ai_clean_title.ilike(f'%{keyword}%'))
            conditions.append(or_(*keyword_conditions))
        
        # Date range
        if search_params.get('date_from'):
            try:
                date_from = datetime.fromisoformat(search_params['date_from'])
                conditions.append(Order.order_date >= date_from)
            except:
                pass
        
        if search_params.get('date_to'):
            try:
                date_to = datetime.fromisoformat(search_params['date_to'])
                conditions.append(Order.order_date <= date_to)
            except:
                pass
        
        # Price range
        if search_params.get('min_price'):
            conditions.append(Order.price >= search_params['min_price'])
        
        if search_params.get('max_price'):
            conditions.append(Order.price <= search_params['max_price'])
        
        # Status
        if search_params.get('status'):
            conditions.append(Order.current_status == search_params['status'])
        
        # Apply conditions
        if conditions:
            query = query.where(and_(*conditions))
        
        # Order by date
        query = query.order_by(Order.order_date.desc()).limit(50)
        
        result = await session.execute(query)
        return result.scalars().all()
    
    async def _generate_response(
        self, 
        user_query: str, 
        orders: List[Order],
        search_params: Dict
    ) -> str:
        """
        Generate natural language response
        """
        if not orders:
            return "I couldn't find any orders matching your query. Try adjusting your search terms or date range."
        
        if not LITELLM_AVAILABLE or not self.model:
            return self._basic_response(orders)
        
        # Prepare order summary for LLM
        order_summaries = []
        for order in orders[:10]:  # Limit to 10 for context
            summary = f"- {order.item_title} (¥{order.price} × {order.quantity})"
            if order.order_date:
                summary += f", ordered on {order.order_date.strftime('%Y-%m-%d')}"
            if order.current_status:
                summary += f", status: {order.current_status}"
            order_summaries.append(summary)
        
        context = f"Found {len(orders)} orders:\n" + "\n".join(order_summaries)
        
        system_prompt = """You are a helpful shopping assistant. Based on the order data provided, 
answer the user's question naturally and conversationally. Include specific details like:
- Item names and brands
- Prices and quantities
- Order dates
- Current status

Be concise but informative."""

        try:
            response = await acompletion(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Query: {user_query}\n\nOrder Data:\n{context}"}
                ],
                temperature=0.7
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            print(f"Error generating response with LLM: {e}")
            return self._basic_response(orders)
    
    def _basic_response(self, orders: List[Order]) -> str:
        """Generate basic response without LLM"""
        if len(orders) == 0:
            return "No orders found matching your query."
        
        response = f"Found {len(orders)} order(s):\n\n"
        
        for order in orders[:5]:  # Show first 5
            response += f"• {order.item_title}\n"
            response += f"  Price: ¥{order.price} × {order.quantity}\n"
            if order.order_date:
                response += f"  Ordered: {order.order_date.strftime('%Y-%m-%d')}\n"
            response += f"  Status: {order.current_status}\n\n"
        
        if len(orders) > 5:
            response += f"... and {len(orders) - 5} more"
        
        return response
