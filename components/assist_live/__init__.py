# SPDX-License-Identifier: GPL-3.0-or-later
import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.const import CONF_ID

assist_live_ns = cg.esphome_ns.namespace("assist_live")
AssistLiveComponent = assist_live_ns.class_("AssistLiveComponent", cg.Component)

CONFIG_SCHEMA = cv.Schema({cv.GenerateID(): cv.declare_id(AssistLiveComponent)}).extend(
    cv.COMPONENT_SCHEMA
)


async def to_code(config):
    component = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(component, config)
