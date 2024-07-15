from hardware_pydantic.junior.junior_devices import *
from hardware_pydantic.junior.settings import *


class JuniorBenchtop(BaseClass):
    is_defined_by_ontology = JuniorOntology
    SLOT_OFF_1: JuniorSlot
    SLOT_OFF_2: JuniorSlot
    SLOT_OFF_3: JuniorSlot

    WASH_BAY: JuniorWashBay

    SLOT_2_3_1: JuniorSlot
    SLOT_2_3_2: JuniorSlot
    SLOT_2_3_3: JuniorSlot

    SLOT_PDT_1: JuniorSlot
    SLOT_PDT_2: JuniorSlot
    SLOT_PDT_3: JuniorSlot

    SV_VIAL_SLOTS: list[JuniorSlot]

    SV_TOOL_SLOT: JuniorSlot

    BALANCE: JuniorSlot

    VPG_SLOT: JuniorSlot

    TIP_DISPOSAL: JuniorTipDisposal

    ARM_Z1: JuniorArmZ1

    ARM_Z2: JuniorArmZ2

    ARM_PLATFORM: JuniorArmPlatform

    SV_TOOL: JuniorSvt

    VPG: JuniorVpg

    PDP_1: JuniorPdp
    PDP_2: JuniorPdp
    PDP_3: JuniorPdp


def create_junior_base():
    assert len(JUNIOR_LAB.dict_object) == 0, "JUNIOR BASE HAS ALREADY BEEN INIT!!!"

    slot_off_1 = JuniorSlot(
        identifier=f"{JuniorOntology.get_namespace_iri()}/SLOT-OFF-1", can_contain=[JuniorRack.get_rdf_type(), ],
        layout=JuniorLayout.from_relative_layout()
    )
    slot_off_2 = JuniorSlot(
        identifier=f"{JuniorOntology.get_namespace_iri()}/SLOT-OFF-2", can_contain=[JuniorRack.get_rdf_type(), ],
        layout=JuniorLayout.from_relative_layout("above", slot_off_1.layout.get_range_assume_one())
    )
    slot_off_3 = JuniorSlot(
        identifier=f"{JuniorOntology.get_namespace_iri()}/SLOT-OFF-3", can_contain=[JuniorRack.get_rdf_type(), ],
        layout=JuniorLayout.from_relative_layout("above", slot_off_2.layout.get_range_assume_one())
    )

    wash_bay = JuniorWashBay(
        identifier=f"{JuniorOntology.get_namespace_iri()}/WASH-BAY",
        layout=JuniorLayout.from_relative_layout("right_to", slot_off_1.layout.get_range_assume_one(), JUNIOR_LAYOUT_SLOT_SIZE_X_SMALL,
                                                 JUNIOR_LAYOUT_SLOT_SIZE_Y * 3)
    )

    slot_2_3_1 = JuniorSlot(
        identifier=f"{JuniorOntology.get_namespace_iri()}/SLOT-2-3-1", can_contain=[JuniorRack.get_rdf_type(), ], can_heat=True, can_cool=True, can_stir=True,
        layout=JuniorLayout.from_relative_layout("right_to", wash_bay.layout.get_range_assume_one())
    )
    slot_2_3_2 = JuniorSlot(
        identifier=f"{JuniorOntology.get_namespace_iri()}/SLOT-2-3-2", can_contain=[JuniorRack.get_rdf_type(), ], can_heat=True, can_stir=True,
        layout=JuniorLayout.from_relative_layout("above", slot_2_3_1.layout.get_range_assume_one())
    )
    slot_2_3_3 = JuniorSlot(
        identifier=f"{JuniorOntology.get_namespace_iri()}/SLOT-2-3-3", can_contain=[JuniorRack.get_rdf_type(), ], can_heat=True, can_stir=True,
        layout=JuniorLayout.from_relative_layout("above", slot_2_3_2.layout.get_range_assume_one())
    )

    slot_pdt_1 = JuniorSlot(
        identifier=f"{JuniorOntology.get_namespace_iri()}/PDT-SLOT-1", can_contain=[JuniorPdp.get_rdf_type(), ],
        layout=JuniorLayout.from_relative_layout("right_to", slot_2_3_1.layout.get_range_assume_one(), JUNIOR_LAYOUT_SLOT_SIZE_X_SMALL * 2,
                                                 JUNIOR_LAYOUT_SLOT_SIZE_Y_SMALL),
    )
    slot_pdt_2 = JuniorSlot(
        identifier=f"{JuniorOntology.get_namespace_iri()}/PDT-SLOT-2", can_contain=[JuniorPdp.get_rdf_type(), ],
        layout=JuniorLayout.from_relative_layout("above", slot_pdt_1.layout.get_range_assume_one(), JUNIOR_LAYOUT_SLOT_SIZE_X_SMALL * 2,
                                                 JUNIOR_LAYOUT_SLOT_SIZE_Y_SMALL),
    )
    slot_pdt_3 = JuniorSlot(
        identifier=f"{JuniorOntology.get_namespace_iri()}/PDT-SLOT-3", can_contain=[JuniorPdp.get_rdf_type(), ],
        layout=JuniorLayout.from_relative_layout("above", slot_pdt_2.layout.get_range_assume_one(), JUNIOR_LAYOUT_SLOT_SIZE_X_SMALL * 2,
                                                 JUNIOR_LAYOUT_SLOT_SIZE_Y_SMALL),
    )

    sv_vial_slots = []

    num_sv_vial_per_row = 3

    for i in range(12):
        irow = i // num_sv_vial_per_row
        icol = i % num_sv_vial_per_row
        if i == 0:
            sv_vial_slot = JuniorSlot(
                identifier=f"{JuniorOntology.get_namespace_iri()}/SVV-SLOT-{i + 1}", can_contain=[JuniorVial.get_rdf_type(), ],
                layout=JuniorLayout.from_relative_layout('above', slot_pdt_3.layout.get_range_assume_one(),
                                                         JUNIOR_LAYOUT_SLOT_SIZE_X_SMALL * 2,
                                                         JUNIOR_LAYOUT_SLOT_SIZE_Y_SMALL),
            )
        else:
            last_slot = sv_vial_slots[i - 1]
            if irow == (i - 1) // num_sv_vial_per_row:
                relation = "right_to"
                relative = last_slot
            else:
                relation = "above"
                relative = sv_vial_slots[i - num_sv_vial_per_row]
            sv_vial_slot = JuniorSlot(
                identifier=f"{JuniorOntology.get_namespace_iri()}/SVV-SLOT-{i + 1}", can_contain=[JuniorVial.get_rdf_type(), ],
                layout=JuniorLayout.from_relative_layout(relation, relative.layout.get_range_assume_one(), JUNIOR_LAYOUT_SLOT_SIZE_X_SMALL * 2,
                                                         JUNIOR_LAYOUT_SLOT_SIZE_Y_SMALL),
            )
        sv_vial_slots.append(sv_vial_slot)

    sv_tool_slot = JuniorSlot(
        identifier=f"{JuniorOntology.get_namespace_iri()}/SV-TOOL-SLOT", can_contain=[JuniorSvt.get_rdf_type(), ],
        layout=JuniorLayout.from_relative_layout('above', sv_vial_slots[9].layout.get_range_assume_one()),
    )

    balance = JuniorSlot(
        identifier=f"{JuniorOntology.get_namespace_iri()}/BALANCE-SLOT", can_contain=[JuniorRack.get_rdf_type(), ], can_weigh=True,
        layout=JuniorLayout.from_relative_layout('right_to', sv_tool_slot.layout.get_range_assume_one()),
    )

    vpg_slot = JuniorSlot(
        identifier=f"{JuniorOntology.get_namespace_iri()}/VPG-SLOT", can_contain=[JuniorVpg.get_rdf_type(), ],
        layout=JuniorLayout.from_relative_layout('right_to', balance.layout.get_range_assume_one(), )
    )

    tip_disposal = JuniorTipDisposal(
        identifier=f"{JuniorOntology.get_namespace_iri()}/DISPOSAL",
        layout=JuniorLayout.from_relative_layout('right_to', vpg_slot.layout.get_range_assume_one(), layout_x=JUNIOR_LAYOUT_SLOT_SIZE_X_SMALL)
    )

    arm_z1 = JuniorArmZ1(
        identifier=f'{JuniorOntology.get_namespace_iri()}/Z1-ARM', contained_by=f'{JuniorOntology.get_namespace_iri()}/ARM-PLATFORM', contained_in_slot="z1",
        can_contain=[JuniorZ1Needle.get_rdf_type(), ],
        has_slot_content=[
            JuniorZ1Needle(identifier=f"{JuniorOntology.get_namespace_iri()}/Z1-Needle-{i + 1}", contained_by=f'{JuniorOntology.get_namespace_iri()}/Z1-ARM',
                           contained_in_slot=str(i + 1), material="STEEL") for i in range(7)
        ],
    )

    arm_z2 = JuniorArmZ2(
        identifier=f'{JuniorOntology.get_namespace_iri()}/Z2-ARM', contained_by=f'{JuniorOntology.get_namespace_iri()}/ARM-PLATFORM', contained_in_slot='z2',
        can_contain=[JuniorSvt.get_rdf_type(), JuniorVpg.get_rdf_type(), JuniorPdp.get_rdf_type(), ],
    )

    arm_platform = JuniorArmPlatform(
        identifier=f'{JuniorOntology.get_namespace_iri()}/ARM-PLATFORM', can_contain=[JuniorArmZ1.get_rdf_type(), JuniorArmZ2.get_rdf_type(), ],
        has_position_on_top_of=slot_off_1.identifier, has_anchor_arm=arm_z1.identifier,
        has_slot_content=[arm_z1, arm_z2],
    )

    sv_tool = JuniorSvt(identifier=f"{JuniorOntology.get_namespace_iri()}/SV-TOOL", contained_by=sv_tool_slot.identifier, powder_param_known=False,
                        contained_in_slot='SLOT')
    sv_tool_slot.has_slot_content.range.add(sv_tool)

    vpg = JuniorVpg(identifier=f"{JuniorOntology.get_namespace_iri()}/VPG", contained_by=vpg_slot.identifier, contained_in_slot='SLOT')
    vpg_slot.has_slot_content.range.add(vpg)

    pdp_1 = JuniorPdp(identifier=f'{JuniorOntology.get_namespace_iri()}/PDT-1', contained_by=slot_pdt_1.identifier, contained_in_slot='SLOT')
    pdp_2 = JuniorPdp(identifier=f'{JuniorOntology.get_namespace_iri()}/PDT-2', contained_by=slot_pdt_2.identifier, contained_in_slot='SLOT')
    pdp_3 = JuniorPdp(identifier=f'{JuniorOntology.get_namespace_iri()}/PDT-3', contained_by=slot_pdt_3.identifier, contained_in_slot='SLOT')
    slot_pdt_1.has_slot_content.range.add(pdp_1)
    slot_pdt_2.has_slot_content.range.add(pdp_2)
    slot_pdt_3.has_slot_content.range.add(pdp_3)

    return JuniorBenchtop(
        SLOT_OFF_1=slot_off_1,
        SLOT_OFF_2=slot_off_2,
        SLOT_OFF_3=slot_off_3,

        WASH_BAY=wash_bay,

        SLOT_2_3_1=slot_2_3_1,
        SLOT_2_3_2=slot_2_3_2,
        SLOT_2_3_3=slot_2_3_3,

        SLOT_PDT_1=slot_pdt_1,
        SLOT_PDT_2=slot_pdt_2,
        SLOT_PDT_3=slot_pdt_3,

        SV_VIAL_SLOTS=sv_vial_slots,

        SV_TOOL_SLOT=sv_tool_slot,

        BALANCE=balance,

        VPG_SLOT=vpg_slot,

        TIP_DISPOSAL=tip_disposal,

        ARM_Z1=arm_z1,

        ARM_Z2=arm_z2,

        ARM_PLATFORM=arm_platform,

        SV_TOOL=sv_tool,

        VPG=vpg,

        PDP_1=pdp_1,
        PDP_2=pdp_2,
        PDP_3=pdp_3,
    )
