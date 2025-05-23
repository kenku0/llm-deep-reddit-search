"""
title: Reddit Search Toolkit
author: Blair Kahn
author_url: https://tsubasa-aviation.ai
git_url: https://github.com/tsubasa-aviation/reddit-search-toolkit
required_open_webui_version: 0.4.0
description: A simple toolkit for searching Reddit posts and fetching top comments without an API key, designed for Open WebUI.
requirements: requests
version: 0.1.0
license: MIT
"""

from __future__ import annotations

import asyncio
import inspect
import time
import typing as _t
import logging

import requests
from pydantic import BaseModel, Field

# It's good practice to have a logger instance for your tool
logger = logging.getLogger(__name__)
# You might want to set a specific level for testing if OpenWebUI's global log level doesn't show it
# logger.setLevel(logging.DEBUG)

__all__ = ["Tools"]


class Tools:
    """Reddit Search Toolkit for Open WebUI.

    Provides two tool methods:
    - **search**: Search Reddit posts matching a query.
    - **get_top_comments**: Retrieve top‑level comments for a Reddit post.

    Both methods optionally stream *status* events so the user sees progress in real time.
    """

    # -------------------------
    #  Valves (user settings)
    # -------------------------
    class Valves(BaseModel):
        """User‑configurable settings for the toolkit."""

        user_agent: str = Field(
            "Mozilla/5.0 (RedditSearchToolkit/0.1.0)",
            description="User‑Agent header sent with each Reddit request."
        )
        max_results: int = Field(
            80,
            ge=1,
            le=150,
            description="Default maximum number of posts returned when *limit* is not provided."
        )

    def __init__(self):
        logger.info("REDDIT_TOOL: Initializing Tools class...")
        print("REDDIT_TOOL: Initializing Tools class...") # Also print for immediate visibility in docker logs
        # Disable automatic citations – we emit our own when desired.
        self.citation = False
        
        try:
            logger.info("REDDIT_TOOL: Attempting to instantiate Valves...")
            print("REDDIT_TOOL: Attempting to instantiate Valves...")
            self.valves = self.Valves()
            logger.info(f"REDDIT_TOOL: Valves instantiated successfully. user_agent='{self.valves.user_agent}', max_results={self.valves.max_results}")
            print(f"REDDIT_TOOL: Valves instantiated successfully. user_agent='{self.valves.user_agent}', max_results={self.valves.max_results}")
        except Exception as e: # Catching Pydantic's ValidationError here specifically would be even better
            logger.error(f"REDDIT_TOOL: ERROR instantiating Valves: {e}", exc_info=True)
            print(f"REDDIT_TOOL: ERROR instantiating Valves: {e}")
            # Optionally re-raise or handle, but for debugging, logging is key
            raise # Re-raise the exception to see if OpenWebUI catches it higher up
            
        logger.info("REDDIT_TOOL: Tools class initialization complete.")
        print("REDDIT_TOOL: Tools class initialization complete.")

    # -------------------------
    #  Helper utilities
    # -------------------------
    def _emit_status(
        self,
        __event_emitter__: _t.Callable[[dict], _t.Any] | None,
        description: str,
        *,
        done: bool = False,
        hidden: bool = False,
    ) -> None:
        """Utility for emitting status updates if an emitter is available."""
        if __event_emitter__ is not None:
            payload = {
                "type": "status",
                "data": {"description": description, "done": done, "hidden": hidden},
            }
            
            returned_value = __event_emitter__(payload)

            if inspect.isawaitable(returned_value):
                try:
                    # Fire-and-forget for async emitters if an event loop is running
                    asyncio.create_task(returned_value)
                except RuntimeError:
                    # Fallback if no event loop is running (e.g., called from a sync context)
                    # This is less likely when _emit_status is called from an async tool method.
                    asyncio.run(returned_value)
            # If not awaitable, it was a synchronous call and has already completed.

    # -------------------------
    #  Tool methods
    # -------------------------
    async def search(
        self,
        query: str,
        sort: str = "relevance",
        time_window: str = "all",
        limit: str = "-1",  # Changed to str, using "-1" as sentinel for default
        __event_emitter__=None, # Removed complex type hint
        **_: _t.Any,
    ) -> list[dict]:
        """Search Reddit for posts matching *query*.

        Parameters
        ----------
        query:
            The free‑text query string.
        sort:
            Reddit sort order – one of ``relevance``, ``hot``, ``top``, ``new``, or ``comments``.
        time_window:
            Time filter – one of ``hour``, ``day``, ``week``, ``month``, ``year``, or ``all``. Ignored for some sort modes.
        limit:
            (String) Maximum number of posts to return. Use "-1" or omit for default (valves.max_results, now 80). Max 150.
        __event_emitter__:
            *Optional.* Injected by Open WebUI.

        Returns
        -------
        list[dict]
            A list of posts.
        """
        print(f"REDDIT_TOOL: ENTERING search. query='{query}' (type: {type(query)}), sort='{sort}' (type: {type(sort)}), limit_str='{limit}' (type: {type(limit)})")
        self._emit_status(__event_emitter__, f"Searching Reddit for ‘{query}’…")

        actual_limit = self.valves.max_results
        try:
            if limit and limit != "-1": # Check if limit is provided and not the sentinel
                parsed_limit = int(limit)
                if 1 <= parsed_limit <= 150: # Changed upper bound from 100 to 150
                    actual_limit = parsed_limit
                else:
                    print(f"REDDIT_TOOL: Provided limit '{limit}' is out of bounds (1-150). Using default: {actual_limit}") # Updated print message
            else:
                 print(f"REDDIT_TOOL: Limit is default sentinel or empty. Using default: {actual_limit}")
        except ValueError:
            print(f"REDDIT_TOOL: Could not parse limit string '{limit}' to int. Using default: {actual_limit}")
        
        print(f"REDDIT_TOOL: Effective limit for API call: {actual_limit}")

        headers = {"User-Agent": self.valves.user_agent}
        params = {
            "q": query,
            "sort": sort,
            "t": time_window,
            "limit": actual_limit, # Use the processed integer limit
            "restrict_sr": False,
            "type": "link",
        }

        response = await asyncio.to_thread(
            requests.get, "https://www.reddit.com/search.json", headers=headers, params=params, timeout=10
        )
        response.raise_for_status()
        data = response.json()

        posts: list[dict] = []
        for child in data.get("data", {}).get("children", []):
            post_data = child.get("data", {})
            posts.append(
                {
                    "title": post_data.get("title"),
                    "subreddit": post_data.get("subreddit"),
                    "url": f"https://www.reddit.com{post_data.get('permalink')}",
                    "score": post_data.get("score"),
                    "num_comments": post_data.get("num_comments"),
                    "created_utc": post_data.get("created_utc"),
                }
            )
            if len(posts) >= actual_limit : # Ensure we don't exceed the intended limit due to Reddit sometimes returning more
                break

        print(f"REDDIT_TOOL: Posts to be returned to LLM ({len(posts)}):")
        for i, p_data in enumerate(posts):
            print(f"  Post {i+1}: Title: {p_data.get('title')}, URL: {p_data.get('url')}")
        self._emit_status(__event_emitter__, f"Retrieved {len(posts)} posts.", done=True)
        print(f"REDDIT_TOOL: EXITING search. Returning {len(posts)} posts.")
        return posts

    async def get_top_comments(
        self,
        post_url: str,
        num_comments: str = "10", # Changed to str, and default to "10"
        __event_emitter__=None, # Removed complex type hint
        **_: _t.Any,
    ) -> list[dict]:
        """Fetch top‑level comments for a Reddit submission.

        Parameters
        ----------
        post_url:
            Full URL of the Reddit submission.
        num_comments:
            (String) Maximum number of comments to return. Default "10".
        __event_emitter__:
            *Optional.* Injected by Open WebUI.

        Returns
        -------
        list[dict]
            A list of comment dictionaries.
        """
        print(f"REDDIT_TOOL: ENTERING get_top_comments. post_url='{post_url}' (type: {type(post_url)}), num_comments_str='{num_comments}' (type: {type(num_comments)})")
        self._emit_status(__event_emitter__, "Fetching comments…")

        actual_num_comments = 10 # Default if parsing fails or invalid, changed from 5 to 10
        try:
            if num_comments:
                parsed_num_comments = int(num_comments)
                if parsed_num_comments > 0 : # Basic validation
                    actual_num_comments = parsed_num_comments
                else:
                    print(f"REDDIT_TOOL: Provided num_comments '{num_comments}' is not positive. Using default: {actual_num_comments}")
            else:
                print(f"REDDIT_TOOL: num_comments is empty. Using default: {actual_num_comments}") # Default is now 10
        except ValueError:
            print(f"REDDIT_TOOL: Could not parse num_comments string '{num_comments}' to int. Using default: {actual_num_comments}")

        print(f"REDDIT_TOOL: Effective num_comments for API call: {actual_num_comments}")

        json_url = post_url.rstrip("/") + ".json"
        headers = {"User-Agent": self.valves.user_agent}
        
        response = await asyncio.to_thread(
            requests.get, json_url, headers=headers, params={"limit": actual_num_comments, "depth": 1}, timeout=10
        )
        response.raise_for_status()
        try:
            payload = response.json()
        except requests.exceptions.JSONDecodeError:
            logger.error(f"REDDIT_TOOL: Failed to decode JSON from {json_url}", exc_info=True)
            print(f"REDDIT_TOOL: Failed to decode JSON from {json_url}. Response text: {response.text[:200]}") # Log start of text
            self._emit_status(__event_emitter__, f"Could not fetch comments for {post_url} (invalid format).", done=True, hidden=True)
            return [] # Return empty list on decode error

        comments: list[dict] = []
        if len(payload) > 1:
            for child in payload[1].get("data", {}).get("children", []):
                if child.get("kind") == "t1":
                    comment_data = child.get("data", {})
                    comments.append(
                        {
                            "author": comment_data.get("author"),
                            "body": comment_data.get("body"),
                            "score": comment_data.get("score"),
                        }
                    )
                    if len(comments) >= actual_num_comments:
                        break

        self._emit_status(__event_emitter__, f"Returned {len(comments)} comments.", done=True)
        print(f"REDDIT_TOOL: EXITING get_top_comments. Returning {len(comments)} comments.")
        return comments

if __name__ == "__main__":
    async def main():
        print("Running RedditSearchToolkit in standalone mode for testing...\n")
        
        toolkit = Tools()

        # --- Test search method ---
        print("Testing search method...")
        search_query = "python programming"
        print(f"Searching for: '{search_query}'")
        try:
            search_results = await toolkit.search(query=search_query, limit="3")
            print("\nSearch Results:")
            if search_results:
                for i, post in enumerate(search_results):
                    print(f"  Post {i+1}:")
                    print(f"    Title: {post.get('title')}")
                    print(f"    Subreddit: {post.get('subreddit')}")
                    print(f"    URL: {post.get('url')}")
                    print(f"    Score: {post.get('score')}")
            else:
                print("  No search results found.")
        except Exception as e:
            print(f"  Error during search: {e}")
        
        print("-" * 30)

        # --- Test get_top_comments method ---
        # You'll need a valid Reddit post URL for this test
        # Example: a popular post from r/python. Replace with a current one if needed.
        # Note: This URL might become invalid over time.
        # post_url_to_test = "https://www.reddit.com/r/Python/comments/10ikcmp/is_it_a_good_idea_to_learn_django_or_flask_in_2023/" # OLD URL
        post_url_to_test = "https://www.reddit.com/r/AskSF/comments/1atv9qp/what_is_currently_the_best_restaurant_in_all_of/" # <-- CHANGE THIS LINE
        # A more generic, less likely to break URL for testing structure (may not always have comments)
        # post_url_to_test = "https://www.reddit.com/r/AskReddit/comments/t0mk0p/what_is_the_most_useless_fact_you_know/"

        print(f"\nTesting get_top_comments method for URL: {post_url_to_test}")
        try:
            comments_results = await toolkit.get_top_comments(post_url=post_url_to_test, num_comments="2")
            print("\nTop Comments:")
            if comments_results:
                for i, comment in enumerate(comments_results):
                    print(f"  Comment {i+1}:")
                    print(f"    Author: {comment.get('author')}")
                    print(f"    Score: {comment.get('score')}")
                    print(f"    Body: {comment.get('body', '')[:100]}...") # Print first 100 chars
            else:
                print("  No comments found or post URL is invalid/inaccessible.")
        except Exception as e:
            print(f"  Error fetching comments: {e}")

    asyncio.run(main())
