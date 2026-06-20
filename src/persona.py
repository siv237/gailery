"""Persona management system for face identification"""

from typing import Dict, Optional, List
from dataclasses import dataclass
from datetime import datetime
import logging
import uuid

from config import PERSONAS_TABLE

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class Persona:
    """Represents a person entity"""
    persona_id: str
    name: str  # Technical name (persona_1, persona_2, etc.)
    display_name: Optional[str] = None  # User-provided display name
    created_at: Optional[str] = None
    face_count: int = 0

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization"""
        return {
            "persona_id": self.persona_id,
            "name": self.name,
            "display_name": self.display_name,
            "created_at": self.created_at or datetime.now().isoformat(),
            "face_count": self.face_count
        }


@dataclass
class FacePersonaMapping:
    """Mapping between face and persona"""
    face_id: str
    persona_id: str

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization"""
        return {
            "face_id": self.face_id,
            "persona_id": self.persona_id
        }


class PersonaManager:
    """Manage personas and face-to-persona mappings"""

    def __init__(self):
        """Initialize persona manager"""
        self.personas: Dict[str, Persona] = {}
        self.face_mappings: Dict[str, str] = {}  # face_id -> persona_id
        self._next_persona_number = 1

    def create_persona(self, display_name: Optional[str] = None) -> Persona:
        """
        Create a new persona with automatic numbering
        
        Args:
            display_name: Optional user-provided name
            
        Returns:
            New Persona object
        """
        persona_id = f"persona_{self._next_persona_number}"
        self._next_persona_number += 1
        
        persona = Persona(
            persona_id=persona_id,
            name=persona_id,
            display_name=display_name,
            created_at=datetime.now().isoformat(),
            face_count=0
        )
        
        self.personas[persona_id] = persona
        logger.info(f"Created persona: {persona_id}")
        return persona

    def assign_face_to_persona(self, face_id: str, persona_id: str) -> bool:
        """
        Assign a face to a persona
        
        Args:
            face_id: Face identifier
            persona_id: Persona identifier
            
        Returns:
            True if assignment successful
        """
        if persona_id not in self.personas:
            logger.warning(f"Persona {persona_id} does not exist")
            return False
        
        if face_id in self.face_mappings:
            logger.warning(f"Face {face_id} already assigned to persona {self.face_mappings[face_id]}")
            return False
        
        self.face_mappings[face_id] = persona_id
        self.personas[persona_id].face_count += 1
        logger.debug(f"Assigned face {face_id} to persona {persona_id}")
        return True

    def get_persona_for_face(self, face_id: str) -> Optional[Persona]:
        """
        Get persona for a face
        
        Args:
            face_id: Face identifier
            
        Returns:
            Persona object or None if not found
        """
        persona_id = self.face_mappings.get(face_id)
        if persona_id:
            return self.personas.get(persona_id)
        return None

    def get_persona(self, persona_id: str) -> Optional[Persona]:
        """
        Get persona by ID
        
        Args:
            persona_id: Persona identifier
            
        Returns:
            Persona object or None if not found
        """
        return self.personas.get(persona_id)

    def get_all_personas(self) -> List[Persona]:
        """
        Get all personas
        
        Returns:
            List of all Persona objects
        """
        return list(self.personas.values())

    def update_persona_display_name(self, persona_id: str, display_name: str) -> bool:
        """
        Update display name for persona
        
        Args:
            persona_id: Persona identifier
            display_name: New display name
            
        Returns:
            True if update successful
        """
        persona = self.personas.get(persona_id)
        if persona:
            persona.display_name = display_name
            logger.info(f"Updated display name for {persona_id} to {display_name}")
            return True
        return False

    def merge_personas(self, source_persona_id: str, target_persona_id: str) -> bool:
        """
        Merge two personas (combine all faces from source into target)
        
        Args:
            source_persona_id: Persona to merge from
            target_persona_id: Persona to merge into
            
        Returns:
            True if merge successful
        """
        if source_persona_id not in self.personas or target_persona_id not in self.personas:
            logger.warning("One or both personas do not exist")
            return False
        
        if source_persona_id == target_persona_id:
            logger.warning("Cannot merge persona with itself")
            return False
        
        # Reassign all faces from source to target
        source_persona = self.personas[source_persona_id]
        target_persona = self.personas[target_persona_id]
        
        faces_to_reassign = [
            face_id for face_id, pid in self.face_mappings.items() 
            if pid == source_persona_id
        ]
        
        for face_id in faces_to_reassign:
            self.face_mappings[face_id] = target_persona_id
        
        # Update face counts
        target_persona.face_count += source_persona.face_count
        source_persona.face_count = 0
        
        logger.info(f"Merged {source_persona_id} into {target_persona_id} ({len(faces_to_reassign)} faces)")
        return True

    def delete_persona(self, persona_id: str) -> bool:
        """
        Delete a persona
        
        Args:
            persona_id: Persona identifier
            
        Returns:
            True if deletion successful
        """
        if persona_id not in self.personas:
            logger.warning(f"Persona {persona_id} does not exist")
            return False
        
        # Remove all face mappings
        faces_to_remove = [
            face_id for face_id, pid in self.face_mappings.items() 
            if pid == persona_id
        ]
        
        for face_id in faces_to_remove:
            del self.face_mappings[face_id]
        
        # Remove persona
        del self.personas[persona_id]
        logger.info(f"Deleted persona {persona_id} ({len(faces_to_remove)} faces unassigned)")
        return True

    def suggest_persona_for_face(self, face_embedding: List[float], threshold: float = 0.5) -> Optional[Persona]:
        """
        Suggest existing persona for a new face based on embedding similarity
        This is a placeholder - actual implementation requires LanceDB
        
        Args:
            face_embedding: Face embedding vector
            threshold: Similarity threshold
            
        Returns:
            Suggested Persona or None if no match
        """
        # This will be implemented with LanceDB for vector similarity search
        # For now, return None (will require manual assignment)
        return None


def main():
    """Main function for testing"""
    manager = PersonaManager()
    
    # Test persona creation
    persona1 = manager.create_persona()
    persona2 = manager.create_persona()
    
    print(f"Created personas: {persona1.persona_id}, {persona2.persona_id}")
    
    # Test face assignment
    manager.assign_face_to_persona("face_1", persona1.persona_id)
    manager.assign_face_to_persona("face_2", persona1.persona_id)
    manager.assign_face_to_persona("face_3", persona2.persona_id)
    
    print(f"Persona {persona1.persona_id} has {persona1.face_count} faces")
    print(f"Persona {persona2.persona_id} has {persona2.face_count} faces")
    
    # Test display name update
    manager.update_persona_display_name(persona1.persona_id, "Test Person")
    print(f"Persona {persona1.persona_id} display name: {persona1.display_name}")
    
    # Test merge
    manager.merge_personas(persona2.persona_id, persona1.persona_id)
    print(f"After merge: {persona1.persona_id} has {persona1.face_count} faces")


if __name__ == "__main__":
    main()
