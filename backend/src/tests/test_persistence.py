import unittest
import requests
import uuid
import time

BASE_URL = "http://127.0.0.1:3000"

class TestChatPersistence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Generate unique credentials for registration
        cls.username = f"user_{uuid.uuid4().hex[:8]}"
        cls.email = f"{cls.username}@example.com"
        cls.password = "Securepass123!"
        cls.token = None
        cls.user_id = None
        cls.headers = {}

        # 1. Register test user
        reg_payload = {
            "username": cls.username,
            "email": cls.email,
            "password": cls.password
        }
        res = requests.post(f"{BASE_URL}/api/auth/register", json=reg_payload)
        assert res.status_code == 201, f"Registration failed: {res.text}"
        data = res.json()
        cls.token = data["token"]
        cls.user_id = data["user_id"]
        cls.headers = {"Authorization": f"Bearer {cls.token}"}

    def test_01_thread_lifecycle(self):
        # A. Create chat thread
        create_res = requests.post(f"{BASE_URL}/api/threads", json={"title": "Initial Thread"}, headers=self.headers)
        self.assertEqual(create_res.status_code, 200)
        thread = create_res.json()["thread"]
        self.assertEqual(thread["title"], "Initial Thread")
        thread_id = thread["id"]

        # B. List chat threads
        list_res = requests.get(f"{BASE_URL}/api/threads", headers=self.headers)
        self.assertEqual(list_res.status_code, 200)
        threads = list_res.json()["threads"]
        self.assertTrue(any(t["id"] == thread_id for t in threads))

        # C. Rename chat thread
        rename_res = requests.patch(f"{BASE_URL}/api/threads/{thread_id}", json={"title": "Updated Topic"}, headers=self.headers)
        self.assertEqual(rename_res.status_code, 200)

        # Verify renaming works
        list_res = requests.get(f"{BASE_URL}/api/threads", headers=self.headers)
        thread_match = next(t for t in list_res.json()["threads"] if t["id"] == thread_id)
        self.assertEqual(thread_match["title"], "Updated Topic")

        # D. Delete thread
        del_res = requests.delete(f"{BASE_URL}/api/threads/{thread_id}", headers=self.headers)
        self.assertEqual(del_res.status_code, 200)

        # Verify deletion works
        list_res = requests.get(f"{BASE_URL}/api/threads", headers=self.headers)
        self.assertFalse(any(t["id"] == thread_id for t in list_res.json()["threads"]))

    def test_02_chat_message_persistence(self):
        # Create thread
        thread_id = requests.post(f"{BASE_URL}/api/threads", json={"title": "Chat Topic"}, headers=self.headers).json()["thread"]["id"]

        # Ingest text document so RAG search has content to query
        ingest_payload = {
            "content": "Alphabet's headquarters is in Mountain View, California.",
            "metadata": {"title": "Company Info", "category": "General"},
            "strategy": "fixed-size",
            "chunkSize": 500,
            "chunkOverlap": 50,
            "threadId": thread_id
        }
        requests.post(f"{BASE_URL}/api/ingest", json=ingest_payload, headers=self.headers)

        # Send query to stream chat
        chat_payload = {
            "question": "Where is Alphabet's headquarters located?",
            "threadId": thread_id,
            "strategy": "fixed-size"
        }
        chat_res = requests.post(f"{BASE_URL}/api/chat", json=chat_payload, headers=self.headers)
        self.assertEqual(chat_res.status_code, 200)

        # Verify stream completed (consume stream body)
        body_text = chat_res.text
        self.assertIn("data: ", body_text)
        self.assertIn("[DONE]", body_text)

        # Fetch messages history for this thread
        msg_res = requests.get(f"{BASE_URL}/api/threads/{thread_id}/messages", headers=self.headers)
        self.assertEqual(msg_res.status_code, 200)
        messages = msg_res.json()["messages"]

        # We expect at least 2 messages: the user question and the assistant response
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(messages[1]["role"], "model")
        self.assertIn("Mountain View", messages[1]["content"])

    def test_03_document_scoping_isolation(self):
        # Create Thread A & Thread B
        thread_a = requests.post(f"{BASE_URL}/api/threads", json={"title": "Thread A"}, headers=self.headers).json()["thread"]["id"]
        thread_b = requests.post(f"{BASE_URL}/api/threads", json={"title": "Thread B"}, headers=self.headers).json()["thread"]["id"]

        # Ingest a text document, attaching it specifically to Thread A
        ingest_payload = {
            "content": "Tesla delivered 443,956 vehicles in Q2 2024.",
            "metadata": {"title": "Tesla Data", "category": "Automotive"},
            "strategy": "fixed-size",
            "chunkSize": 500,
            "chunkOverlap": 50,
            "threadId": thread_a
        }
        ingest_res = requests.post(f"{BASE_URL}/api/ingest", json=ingest_payload, headers=self.headers)
        doc_id = ingest_res.json()["documentId"]

        # Verify document exists in User Library
        lib_res = requests.get(f"{BASE_URL}/api/documents", headers=self.headers)
        docs = lib_res.json()["documents"]
        self.assertTrue(any(d["id"] == doc_id for d in docs))

        # Run query inside Thread A (attached document)
        search_a = requests.post(
            f"{BASE_URL}/api/search", 
            json={"query": "How many vehicles did Tesla deliver?", "threadId": thread_a, "strategy": "fixed-size"}, 
            headers=self.headers
        )
        self.assertEqual(search_a.status_code, 200)
        self.assertGreater(len(search_a.json()["results"]), 0)

        # Run query inside Thread B (unattached document)
        # Wait, the search tab in the UI doesn't pass threadId (searches everything). But if we pass threadId:
        search_b = requests.post(
            f"{BASE_URL}/api/search", 
            json={"query": "How many vehicles did Tesla deliver?", "threadId": thread_b, "strategy": "fixed-size"}, 
            headers=self.headers
        )
        self.assertEqual(search_b.status_code, 200)
        self.assertEqual(len(search_b.json()["results"]), 0)  # Should return 0 matches since no docs attached to Thread B!

        # Attach the document to Thread B
        requests.post(f"{BASE_URL}/api/threads/{thread_b}/documents", json={"documentId": doc_id}, headers=self.headers)

        # Run query inside Thread B again
        search_b_retry = requests.post(
            f"{BASE_URL}/api/search", 
            json={"query": "How many vehicles did Tesla deliver?", "threadId": thread_b, "strategy": "fixed-size"}, 
            headers=self.headers
        )
        self.assertEqual(search_b_retry.status_code, 200)
        self.assertGreater(len(search_b_retry.json()["results"]), 0)  # Now it retrieves it!

        # Detach document from Thread B
        requests.delete(f"{BASE_URL}/api/threads/{thread_b}/documents/{doc_id}", headers=self.headers)

        # Query Thread B again
        search_b_final = requests.post(
            f"{BASE_URL}/api/search", 
            json={"query": "How many vehicles did Tesla deliver?", "threadId": thread_b, "strategy": "fixed-size"}, 
            headers=self.headers
        )
        self.assertEqual(len(search_b_final.json()["results"]), 0)  # Isolated again!

if __name__ == "__main__":
    unittest.main()
