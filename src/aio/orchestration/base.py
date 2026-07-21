from abc import ABC, abstractmethod
from typing import Any, Dict

class OrchestratorInterface(ABC):
    
    @abstractmethod
    def run(self, goal: str, **kwargs) -> Dict[str, Any]:
        """Execute a mission end-to-end."""
        pass
        
    @abstractmethod
    def resume(self, project_id: str, **kwargs) -> Dict[str, Any]:
        """Resume a mission."""
        pass
