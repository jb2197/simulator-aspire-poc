from __future__ import annotations

from typing import Any, Literal, Type, ClassVar

from N2G import drawio_diagram  # only used for drawing instruction DAG
from pydantic import Field

from twa.data_model.base_ontology import KnowledgeGraph
from twa.data_model.base_ontology import BaseOntology
from twa.data_model.base_ontology import BaseClass
from twa.data_model.base_ontology import ObjectProperty
from twa.data_model.base_ontology import DatatypeProperty
from twa.data_model.base_ontology import as_range


from .utils import str_uuid

DEVICE_ACTION_METHOD_PREFIX = "action__"
DEVICE_ACTION_METHOD_ACTOR_TYPE = Literal['pre', 'post', 'proj']


class JuniorOntology(BaseOntology):
    base_url = "https://junior/kg/"
    namespace = "junior"
    owl_versionInfo = "0.0.1"
    rdfs_comment = 'This is an ontology for the Junior platform from NCATS.'


class Individual(BaseClass):
    """ a thing with an identifier """
    is_defined_by_ontology = JuniorOntology
    instance_iri: str = Field(default=None, alias='identifier')

    @property
    def identifier(self) -> str:
        return self.instance_iri

class Material(DatatypeProperty):
    is_defined_by_ontology = JuniorOntology
    range: as_range(str)

class LabObject(Individual):
    """
    a physical object in a lab that
    1. is not a chemical designed to participate in reactions
    2. has constant, physically defined 3D boundary
    3. has a (non empty) set of measurable qualities that need to be tracked, this set is the state of this `LabObject`
        # TODO can we have a pydantic model history tracker? similar to https://pypi.org/project/pydantic-changedetect/
        # TODO mutable fields vs immutable fields?
    """

    material: Material

    @property
    def state(self) -> dict:
        d = {}
        for k, v in self.__dict__.items():
            if k.startswith("layout"):
                continue
            d[k] = v
        return d

    def validate_state(self, state: dict) -> bool:
        pass

    def validate_current_state(self) -> bool:
        return self.validate_state(self.state)


class PreActError(Exception):
    pass


class PostActError(Exception):
    pass


class Device(LabObject):
    """
    a `LabObject` that
    1. can receive instructions
    2. can change its state and other lab objects' states using its action methods,
    3. cannot change another device's state # TODO does this actually matter?
    """

    def model_post_init(self, __context: Any) -> None:
        # NOTE adding this as it seems to be necessary for other actually overwritten methods to work when multi-inheritance is used
        # i.e. JuniorLabObject and JuniorInstruction
        return super().model_post_init(__context)

    @property
    def action_names(self) -> list[str]:
        """ a sorted list of the names of all defined actions """
        names = sorted(
            {k[len(DEVICE_ACTION_METHOD_PREFIX):] for k in dir(self) if k.startswith(DEVICE_ACTION_METHOD_PREFIX)}
        )
        return names

    def action__dummy(
            self,
            actor_type: DEVICE_ACTION_METHOD_ACTOR_TYPE = 'pre',
            **kwargs
    ) -> tuple[list[LabObject], float] | None:
        """
        ACTION: dummy
        DESCRIPTION: wait for certain amount of time
        PARAMS:
        """
        assert 'actor_type' not in kwargs
        if actor_type == 'pre':
            # the pre actor method of an action should
            # - check the current states of involved objects, raise PreActorError if not met
            return
        elif actor_type == 'post':
            # the post actor method of an action should
            # - make state transitions for involved objects, raise PostActorError if illegal transition
            return
        elif actor_type == 'proj':
            # the projection method of an action should
            # - return a list of all involved objects, except self
            # - return the projected time cost
            return [], 0
        else:
            raise ValueError

    def act(
            self,
            action_name: str = "dummy",
            actor_type: Literal['pre', 'post', 'proj'] = 'pre',
            action_parameters: dict[str, Any] = None,
    ):
        assert action_name in self.action_names, f"{action_name} not in {self.action_names}"
        if action_parameters is None:
            action_parameters = dict()
        method_name = DEVICE_ACTION_METHOD_PREFIX + action_name
        return getattr(self, method_name)(actor_type=actor_type, **action_parameters)

    def act_by_instruction(self, i: Instruction, actor_type: DEVICE_ACTION_METHOD_ACTOR_TYPE):
        """ perform action with an instruction """
        assert i.send_to_device.get_range_assume_one() == self
        return self.act(action_name=i.action_name.get_range_assume_one(), action_parameters=i.action_parameters, actor_type=actor_type)

from typing import List


class Send_to_device(ObjectProperty):
    is_defined_by_ontology = JuniorOntology
    range: as_range(Device)


class Action_name(DatatypeProperty):
    is_defined_by_ontology = JuniorOntology
    range: as_range(str)


class Description(DatatypeProperty):
    is_defined_by_ontology = JuniorOntology
    range: as_range(str)


class Preceding_instructions(ObjectProperty):
    is_defined_by_ontology = JuniorOntology
    range: as_range(Instruction)


class Instruction(Individual):
    """
    an instruction sent to a device for an action

    instruction:
    - an instruction is sent to and received by one and only one `Device` instance (the `actor`) instantly
    - an instruction requests one and only one `action_name` from the `Device` instance
    - an instruction contains static parameters that the `action_method` needs
    - an instruction can involve zero or more `LabObject` instances
    - an instruction cannot involve any `Device` instance except the `actor`

    action:
    - an action is a physical process performed following an instruction
    - an action
        - starts when
            - the actor is available, and
            - the action is at the top of the queue of that actor
        - ends when
            - the duration, returned by the action method of the actor, has passed
    """
    send_to_device: Send_to_device
    action_parameters: dict = dict() # TODO how to define this as the object property?
    action_name: Action_name
    description: Description

    # preceding_type: Literal["ALL", "ANY"] = "ALL"
    # # TODO this has no effect as it is not passed to casymda
    # TODO shall we remove it as it is not used?

    preceding_instructions: Preceding_instructions

    def as_dict(self, identifier_only=True):
        if identifier_only:
            d = self.model_dump()
            dict_action_parameters = dict()
            for k, v in self.action_parameters.items():
                if isinstance(v, LabObject):
                    dict_action_parameters[k] = v.identifier
            d['action_parameters'] = dict_action_parameters
            return d
        else:
            self.model_dump()


class Has_instruction(ObjectProperty):
    is_defined_by_ontology = JuniorOntology
    range: as_range(Instruction)


class Has_lab_object(ObjectProperty):
    is_defined_by_ontology = JuniorOntology
    range: as_range(LabObject)

from pydantic import create_model
class Lab(BaseClass):
    is_defined_by_ontology = JuniorOntology
    has_instruction: Has_instruction
    has_lab_object: Has_lab_object

    def __getitem__(self, identifier: str):
        return self.dict_object[identifier]

    def __setitem__(self, key, value):
        raise NotImplementedError

    @property
    def dict_instruction(self):
        return {i.identifier: i for i in self.has_instruction.range}

    @property
    def dict_object(self):
        return {i.identifier: i for i in self.has_lab_object.range}

    def act_by_instruction(self, i: Instruction, actor_type: DEVICE_ACTION_METHOD_ACTOR_TYPE):
        actor = self.dict_object[i.send_to_device.identifier]  # make sure we are working on the same device
        assert isinstance(actor, Device)
        return actor.act_by_instruction(i, actor_type=actor_type)

    def add_instruction(self, i: Instruction):
        assert i.identifier not in self.has_instruction.range
        self.has_instruction.range.add(i)

    def remove_instruction(self, i: Instruction | str):
        assert i in self.has_instruction.range
        self.has_instruction.range.remove(i)

    def add_object(self, d: LabObject | Device):
        assert d.identifier not in self.dict_object
        self.has_lab_object.range.add(d)

    def remove_object(self, d: LabObject | Device | str):
        assert d in self.has_lab_object.range
        self.has_lab_object.range.remove(d)

    @property
    def state(self) -> dict[str, dict[str, Any]]:
        return {d.identifier: d.state for d in self.dict_object.values()}

    def dict_object_by_class(self, object_class: Type):
        return {k: v for k, v in self.dict_object.items() if v.__class__ == object_class}

    def __repr__(self):
        return "\n".join([f"{obj.identifier}: {obj.state}" for obj in self.dict_object.values()])

    def __str__(self):
        return self.__repr__()

    @property
    def instruction_graph(self) -> drawio_diagram:
        diagram = drawio_diagram()
        diagram.add_diagram("Page-1")

        for k, ins in self.dict_instruction.items():
            diagram.add_node(id=f"{ins.identifier}\n{ins.description}")

        for ins in self.dict_instruction.values():
            for dep in ins.preceding_instructions.range:
                pre_ins = self.dict_instruction[dep]
                this_ins_node = f"{ins.identifier}\n{ins.description}"
                pre_ins_node = f"{pre_ins.identifier}\n{pre_ins.description}"
                diagram.add_link(pre_ins_node, this_ins_node, style="endArrow=classic")
        return diagram
