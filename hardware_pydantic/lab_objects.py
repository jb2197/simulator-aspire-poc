from __future__ import annotations

from typing import Type

from hardware_pydantic.base import Lab, LabObject, JuniorOntology, Individual, Material
from twa.data_model.base_ontology import BaseClass, ObjectProperty, DatatypeProperty, as_range


class Volume_capacity(DatatypeProperty):
    is_defined_by_ontology = JuniorOntology
    range: as_range(float)

class Chemical_name(DatatypeProperty):
    is_defined_by_ontology = JuniorOntology
    range: as_range(str)

class Amount(DatatypeProperty):
    is_defined_by_ontology = JuniorOntology
    range: as_range(float)

class ChemicalContent(Individual):
    is_defined_by_ontology = JuniorOntology
    chemical_name: Chemical_name
    amount: Amount

    def __init__(self, **data):
        # NOTE this is a workaround to make sure the value is casted to float
        if 'amount' in data:
            data['amount'] = float(data['amount'])
        super().__init__(**data)

class Has_chemical_content(ObjectProperty):
    is_defined_by_ontology = JuniorOntology
    range: as_range(ChemicalContent)

    def get_content(self, chemical_name: str) -> ChemicalContent | None:
        for c in self.range:
            if c.chemical_name.get_range_assume_one() == chemical_name:
                return c
        return None

class ChemicalContainer(LabObject):
    """
    a container that is designed to be in direct contact with (reaction-participating) chemicals

    subclass of [container](http://purl.allotrope.org/ontologies/equipment#AFE_0000407)
    """

    volume_capacity: Volume_capacity = Volume_capacity(range=40.0)

    material: Material = Material(range="GLASS")

    has_chemical_content: Has_chemical_content
    # chemical_content: dict[str, float] = dict()
    """ what is inside now? """

    def model_post_init(self, __context) -> None:
        # NOTE adding this as it seems to be necessary for other actually overwritten methods to work when multi-inheritance is used
        # i.e. JuniorLabObject and JuniorInstruction
        return super().model_post_init(__context)

    @property
    def chemical_content(self) -> dict[str, float]:
        return {c.chemical_name.get_range_assume_one(): c.amount.get_range_assume_one() for c in self.has_chemical_content.range}

    @property
    def content_sum(self) -> float:
        if len(self.chemical_content) == 0:
            return 0
        return sum(self.chemical_content.values())

    def add_content(self, content: dict[str, float]):
        for k, v in content.items():
            if k not in self.chemical_content:
                self.has_chemical_content.range.add(ChemicalContent(chemical_name=k, amount=v))
            else:
                self.has_chemical_content.get_content(k).amount.range = {self.has_chemical_content.get_content(k).amount.get_range_assume_one() + content[k]}

    def remove_content(self, amount: float) -> dict[str, float]:
        # by default the content is homogeneous liquid
        pct = amount / self.content_sum
        removed = dict()
        for k in self.chemical_content:
            removed[k] = self.chemical_content[k] * pct
            self.has_chemical_content.get_content(k).amount.range = {self.has_chemical_content.get_content(k).amount.get_range_assume_one() - removed[k]}
        return removed


class Can_contain(ObjectProperty):
    is_defined_by_ontology = JuniorOntology
    range: as_range(LabObject)


class Capacity(DatatypeProperty):
    is_defined_by_ontology = JuniorOntology
    range: as_range(int)


class Has_slot_content(ObjectProperty):
    is_defined_by_ontology = JuniorOntology
    range: as_range(LabObject)

class LabContainer(LabObject):
    """
    a container designed to hold other LabObject instances, such as a vial plate

    it should have a finite, fixed number of slots

    subclass of [container](http://purl.allotrope.org/ontologies/equipment#AFE_0000407)
    """

    def model_post_init(self, __context) -> None:
        # NOTE adding this as it seems to be necessary for other actually overwritten methods to work when multi-inheritance is used
        # i.e. JuniorLabObject and JuniorInstruction
        return super().model_post_init(__context)

    can_contain: Can_contain
    """ the class names of the thing it can hold """
    # TODO validation

    capacity: Capacity
    has_slot_content: Has_slot_content

    @property
    def slot_content(self):
        """ dict[<slot identifier>, <object identifier>] """
        if len(self.has_slot_content.range) == 0:
            return {'SLOT': None}
        else:
            return {k.contained_in_slot: k.identifier for k in self.has_slot_content.range}

    @property
    def empty_slot_keys(self):
        lst = [str(k+1) for k in range(self.slot_capacity)]
        for k in self.has_slot_content.range:
            if k.contained_in_slot in lst:
                lst.remove(k.contained_in_slot)
            else:
                lst = lst[:-1]
        return lst

    @property
    def slot_capacity(self):
        return self.capacity.get_range_assume_one()

    @classmethod
    def from_capacity(cls, can_contain: list[str], capacity: int = 16, container_id: str = None, **kwargs) -> LabContainer:
        # content = {str(i + 1): None for i in range(capacity)}
        if container_id is None:
            return cls(capacity=capacity, can_contain=can_contain, **kwargs)
        else:
            return cls(capacity=capacity, identifier=container_id, can_contain=can_contain, **kwargs)

    @staticmethod
    def get_all_containees(container: LabContainer, lab: Lab) -> list[str]:
        """
        if we are requesting a container as a resource, we should always also request its containees
        ex. if an arm is trying to move a plate while another arm is aspirating liquid from a vial on this plate,
        the former arm should wait for the vial until it is released by the aspiration action
        """
        containees = []
        for containee in container.slot_content.values():
            if containee is None:
                continue
            containees.append(containee)
            if isinstance(lab[containee], LabContainer):
                containees += LabContainer.get_all_containees(lab[containee], lab)
        return containees


class Is_contained_by(ObjectProperty):
    is_defined_by_ontology = JuniorOntology
    range: as_range(LabObject)


class LabContainee(LabObject):
    """
    lab objects that can be held by another lab container

    related to [containing](http://purl.allotrope.org/ontologies/process#AFP_0003623)
    """
    def model_post_init(self, __context) -> None:
        # NOTE adding this as it seems to be necessary for other actually overwritten methods to work when multi-inheritance is used
        # i.e. JuniorLabObject and JuniorInstruction
        return super().model_post_init(__context)

    contained_by: str | None = None

    contained_in_slot: str | None = "SLOT"

    @staticmethod
    def move(containee: LabContainee, dest_container: LabContainer, lab: Lab, dest_slot: str = "SLOT"):
        if containee.contained_by is not None:
            source_container = lab[containee.contained_by]
            source_container: LabContainer
            assert source_container.slot_content[containee.contained_in_slot] == containee.identifier
            source_container.has_slot_content.range.remove(containee)
        assert dest_container.slot_content[dest_slot] is None
        dest_container.has_slot_content.range.add(containee)
        containee.contained_by = dest_container.identifier
        containee.contained_in_slot = dest_slot

    @staticmethod
    def get_container(containee: LabContainee, lab: Lab, upto: Type = None) -> LabContainer | None:
        current_container_id = containee.contained_by
        if current_container_id is None:
            return containee
        else:
            current_container = lab[current_container_id]
            if upto is not None and isinstance(current_container, upto):
                return current_container
            elif isinstance(current_container, LabContainee):
                return LabContainee.get_container(current_container, lab)
            else:
                return current_container
