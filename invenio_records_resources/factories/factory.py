# -*- coding: utf-8 -*-
#
# This file is part of Invenio.
# Copyright (C) 2020 CERN.
# Copyright (C) 2020 Northwestern University.
#
# Invenio-Records-Resources is free software; you can redistribute it and/or
# modify it under the terms of the MIT License; see LICENSE file for more
# details.

"""Record type factory."""
from invenio_db import db
from invenio_pidstore.providers.recordid_v2 import RecordIdProviderV2
from invenio_records.dumpers import ElasticsearchDumper
from invenio_records.models import RecordMetadataBase
from invenio_records.systemfields import ConstantField
from invenio_records_permissions import RecordPermissionPolicy

from invenio_records_resources.factories.record_links_schema import \
    RecordLinksSchemaMeta
from invenio_records_resources.factories.record_search_link_schema import \
    RecordSearchLinksSchemaMeta
from invenio_records_resources.records.api import Record
from invenio_records_resources.records.systemfields import IndexField, PIDField
from invenio_records_resources.resources import RecordResource, \
    RecordResourceConfig
from invenio_records_resources.services import RecordService, \
    RecordServiceConfig


class RecordTypeFactory(object):
    """Factory of record types."""

    model_cls = None
    record_cls = None
    resource_cls = None
    resource_config_cls = None
    service_config_cls = None
    service_cls = None

    _schema_path_template = (
        "https://localhost/schemas/{name_plural}/{name}-v{version}.json"
    )
    _index_name_template = "{name_plural}-{name}-v{version}"

    def __init__(
        self,
        record_type_name,
        record_type_service_schema,
        schema_version="1.0.0",
        endpoint_route=None,
        record_dumper=None,
        schema_path=None,
        index_name=None,
        search_facets_options=None,
        service_components=None,
        permission_policy_cls=None,
    ):
        """Constructor."""
        self.record_type_name = record_type_name
        self.record_name_lower = record_type_name.lower()
        self.name_plural = f"{self.record_name_lower}s"

        # record class attributes
        self.schema_version = schema_version
        self.record_dumper = record_dumper
        self.schema_path = self._build_schema_path(schema_path)
        self.index_name = self._build_index_name(index_name)

        # resource class attributes
        self.endpoint_route = endpoint_route

        # service attributes
        self.record_type_service_schema = record_type_service_schema
        self.search_facets_options = search_facets_options \
            if search_facets_options else {}
        self.service_components = service_components
        self.permission_policy_cls = permission_policy_cls

        self.validate()

        self.create_record_type()

    def _build_schema_path(self, optional_schema_path):
        """Build path for jsonschema."""
        if optional_schema_path:
            return optional_schema_path
        return self._schema_path_template.format(
            name_plural=self.name_plural,
            name=self.record_name_lower,
            version=self.schema_version,
        )

    def _build_index_name(self, index_name):
        """Build index name."""
        if index_name:
            return index_name
        return self._index_name_template.format(
            name_plural=self.name_plural,
            name=self.record_name_lower,
            version=self.schema_version,
        )

    def validate(self):
        """Validate parameters."""
        # TODO - specify what should be validated
        pass

    def create_record_type(self):
        """Create the record type."""
        # methods should call in this order, since classes have dependencies
        self.create_metadata_model()
        self.create_record_class()
        self.create_resource_class()
        self.create_service_class()

    def create_metadata_model(self):
        """Create metadata model."""
        self.model_cls = type(
            f"{self.record_type_name}Metadata",
            (db.Model, RecordMetadataBase),
            dict(
                __tablename__=f"{self.record_name_lower}_metadata",
            ),
        )

    def create_record_class(self):
        """Create record class."""
        record_class_attributes = {
            "model_cls": self.model_cls,
            "schema": ConstantField("$schema", self.schema_path),
            "index": IndexField(self.index_name),
            "pid": PIDField("id", provider=RecordIdProviderV2),
            "dumper": self.record_dumper or ElasticsearchDumper(),
        }
        self.record_cls = type(
            self.record_type_name, (Record,), record_class_attributes
        )

    def _create_links_schemas_class(self, list_route):
        """Create schema link classes."""
        record_link_schema_cls = RecordLinksSchemaMeta(
            {}, self.record_type_name, list_route
        )
        record_search_link_schema_cls = RecordSearchLinksSchemaMeta(
            {}, self.record_type_name, list_route
        )

        return record_link_schema_cls, record_search_link_schema_cls

    def create_resource_class(self):
        """Create resource class."""
        resource_config_cls_name = f"{self.record_type_name}ResourceConfig"
        resource_cls_name = f"{self.record_type_name}Resource"

        list_route = self.endpoint_route or f"/{self.record_name_lower}s"
        item_route = f"{list_route}/<pid_value>"

        (
            record_link_schema_cls,
            record_search_link_schema_cls,
        ) = self._create_links_schemas_class(list_route)

        config_cls_attributes = {
            "list_route": list_route,
            "item_route": item_route,
            "links_config": {
                "record": record_link_schema_cls,
                "search": record_search_link_schema_cls,
            },
        }

        self.resource_config_cls = type(
            resource_config_cls_name,
            (RecordResourceConfig,),
            config_cls_attributes,
        )
        resource_cls_attributes = {"default_config": self.resource_config_cls}

        self.resource_cls = type(
            resource_cls_name, (RecordResource,), resource_cls_attributes
        )

    def create_service_class(self):
        """Create service class."""
        permission_policy_cls_name = f"{self.record_type_name}PermissionPolicy"
        config_cls_name = f"{self.record_type_name}ServiceConfig"
        service_cls_name = f"{self.record_type_name}Service"

        # if permission policy not given, create a standard one
        if not self.permission_policy_cls:
            self.permission_policy_cls = type(
                permission_policy_cls_name, (RecordPermissionPolicy,), {}
            )

        config_cls_attributes = {
            "permission_policy_cls": self.permission_policy_cls,
            "record_cls": self.record_cls,
            "search_facets_options": self.search_facets_options,
            "schema": self.record_type_service_schema,
        }
        if self.service_components:
            config_cls_attributes.update(
                {
                    "components": RecordServiceConfig.components
                    + self.service_components
                }
            )

        self.service_config_cls = type(
            config_cls_name, (RecordServiceConfig,), config_cls_attributes
        )

        service_cls_attributes = {"default_config": self.service_config_cls}
        self.service_cls = type(
            service_cls_name, (RecordService,), service_cls_attributes
        )
