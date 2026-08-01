from datetime import UTC, datetime

from dma import Memory, MemoryType, RecallResult
from dma_mcp import DMATools


class Fake:
    def __init__(self): self.deleted = []
    def remember(self, **kwargs): return memory(kwargs["content"])
    def recall(self, **kwargs):
        m = memory("User prefers Java.")
        return [RecallResult(m.id, m.agent_id, m.content, m.type, m.version, m.status, m.created_at, m.updated_at, m.expires_at, m.metadata, 1.0)]
    def forget(self, item): self.deleted.append(item)

def memory(content):
    now = datetime.now(UTC)
    return Memory("mem_1", "mcp-agent", content, MemoryType.SEMANTIC, 1, "active", now, now, None, {})

def test_tools_delegate_and_return_json_safe_data():
    fake = Fake(); tools = DMATools(fake)
    assert tools.remember("fact", "semantic")["id"] == "mem_1"
    assert tools.recall("Java")["results"][0]["score"] == 1.0
    assert tools.forget("mem_1") == {"deleted": True}
    assert fake.deleted == ["mem_1"]
