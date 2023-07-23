#  Copyright 2022 VMware, Inc.
#  SPDX-License-Identifier: Apache-2.0
import sys
import json
from typing import List

import aria.ops.adapter_logging as logging
import psutil
import constants
import requests
from aria.ops.adapter_instance import AdapterInstance
from aria.ops.data import Metric
from aria.ops.data import Property
from aria.ops.object import Identifier
from aria.ops.definition.adapter_definition import AdapterDefinition
from aria.ops.definition.units import Units
from aria.ops.result import CollectResult
from aria.ops.result import EndpointResult
from aria.ops.result import TestResult
from aria.ops.timer import Timer
from constants import ADAPTER_KIND
from constants import ADAPTER_NAME
from constants import FQDN_IDENTIFIER
from constants import API_IDENTIFIER
from constants import PORT_IDENTIFIER
from helpers import RoadworkProcessor

logger = logging.getLogger(__name__)


def get_adapter_definition() -> AdapterDefinition:
    with Timer(logger, "Get Adapter Definition"):
        definition = AdapterDefinition(ADAPTER_KIND, ADAPTER_NAME)
        
        definition.define_string_parameter(
            constants.FQDN_IDENTIFIER, "Bundesautobahn API Endpoint", default="verkehr.autobahn.de", description="FQDN or IP address of the Bundesautobahn API Endpoint."
        )
        
        definition.define_string_parameter(
            constants.API_IDENTIFIER, "Bundesautobahn API Base URL", default="/o/autobahn", description="Base URL for the API Calls."
        )
        
        definition.define_string_parameter(
            constants.PORT_IDENTIFIER, "TCP Port", default="443"
        )
        
        definition.define_int_parameter(
            "container_memory_limit",
            label="Adapter Memory Limit (MB)",
            description="Sets the maximum amount of memory VMware Aria Operations can "
            "allocate to the container running this adapter instance.",
            required=True,
            advanced=True,
            default=1024,
        )

        autobahn = definition.define_object_type(
            "my_autobahn_resource_kind", "Autobahn")
        autobahn.define_string_identifier("autobahn_id", "AutobahnID")
        
        baustelle = definition.define_object_type(
            "my_roadwork_resource_kind", "Baustelle")
        baustelle.define_string_identifier("baustellen_id", "BaustellenID")

        logger.debug(f"Returning adapter definition: {definition.to_json()}")
        return definition


def test(adapter_instance: AdapterInstance) -> TestResult:
    with Timer(logger, "Test"):
        result = TestResult()
        try:
            fqdn = adapter_instance.get_identifier_value(FQDN_IDENTIFIER)
            api = adapter_instance.get_identifier_value(API_IDENTIFIER)
            port = adapter_instance.get_identifier_value(PORT_IDENTIFIER)
            
            api_url = "https://" + fqdn + ":" + port + api
            response = requests.get(api_url)

            if fqdn is None:
                result.with_error("No URL Found.")
            elif fqdn.lower() == "bad":
                result.with_error("The URL is bad")
        except Exception as e:
            logger.error("Unexpected connection test error")
            logger.exception(e)
            result.with_error("Unexpected connection test error: " + repr(e))
        finally:
            logger.debug(f"Returning test result: {result.get_json()}")
            return result


def collect(adapter_instance: AdapterInstance) -> CollectResult:
    with Timer(logger, "Collection"):
        result = CollectResult()
        try:
            fqdn = adapter_instance.get_identifier_value(FQDN_IDENTIFIER)
            api = adapter_instance.get_identifier_value(API_IDENTIFIER)
            port = adapter_instance.get_identifier_value(PORT_IDENTIFIER)

            api_url = "https://" + fqdn + ":" + port + api
            response = requests.get(api_url)
            my_objects_list = []
            
            if response.status_code == 200:
                data = response.json()
                roads = data["roads"]

                for road in roads:
                    logger.debug(road)
                    autobahn_id = road
                    autobahn = result.object(
                        ADAPTER_KIND, "my_autobahn_resource_kind", road, identifiers=[
                            Identifier("autobahn_id", autobahn_id)
                        ])
                    my_objects_list.append(autobahn)
                    
                    roadworks_url = api_url + "/" + autobahn_id + "/services/roadworks"
                    response = requests.get(roadworks_url)
                    
                    if response.status_code == 200:
                        data = response.json()
                        roadworks = data["roadworks"]

                        for roadwork in roadworks:
                            logger.debug(roadwork)
                            roadwork_title = roadwork["title"]
                            roadwork_id = roadwork["identifier"]
                            baustelle = result.object(
                                ADAPTER_KIND, "my_roadwork_resource_kind", roadwork_title, identifiers=[
                                    Identifier("baustellen_id", roadwork_id)
                                ])
                            my_objects_list.append(baustelle)
            
            result.add_objects(my_objects_list)
                    
        except Exception as e:
            # TODO: If any connections are still open, make sure they are closed before returning
            logger.error("Unexpected collection error")
            logger.exception(e)
            result.with_error("Unexpected collection error: " + repr(e))
        finally:
            logger.debug(vars(result))
            logger.debug(f"Returning collection result {result.get_json()}")
            return result


def get_endpoints(adapter_instance: AdapterInstance) -> EndpointResult:
    with Timer(logger, "Get Endpoints"):
        result = EndpointResult()
        # In the case that an SSL Certificate is needed to communicate to the target,
        # add each URL that the adapter uses here. Often this will be derived from a
        # 'host' parameter in the adapter instance. In this Adapter we don't use any
        # HTTPS connections, so we won't add any. If we did, we might do something like
        # this:
        # result.with_endpoint(adapter_instance.get_identifier_value("host"))
        #
        # Multiple endpoints can be returned, like this:
        # result.with_endpoint(adapter_instance.get_identifier_value("primary_host"))
        # result.with_endpoint(adapter_instance.get_identifier_value("secondary_host"))
        #
        # This 'get_endpoints' method will be run before the 'test' method,
        # and VMware Aria Operations will use the results to extract a certificate from
        # each URL. If the certificate is not trusted by the VMware Aria Operations
        # Trust Store, the user will be prompted to either accept or reject the
        # certificate. If it is accepted, the certificate will be added to the
        # AdapterInstance object that is passed to the 'test' and 'collect' methods.
        # Any certificate that is encountered in those methods should then be validated
        # against the certificate(s) in the AdapterInstance.
        logger.debug(f"Returning endpoints: {result.get_json()}")
        return result


# Main entry point of the adapter. You should not need to modify anything below this line.
def main(argv: List[str]) -> None:
    logging.setup_logging("adapter.log")
    # Start a new log file by calling 'rotate'. By default, the last five calls will be
    # retained. If the logs are not manually rotated, the 'setup_logging' call should be
    # invoked with the 'max_size' parameter set to a reasonable value, e.g.,
    # 10_489_760 (10MB).
    logging.rotate()
    logger.info(f"Running adapter code with arguments: {argv}")
    if len(argv) != 3:
        # `inputfile` and `outputfile` are always automatically appended to the
        # argument list by the server
        logger.error("Arguments must be <method> <inputfile> <ouputfile>")
        exit(1)

    method = argv[0]
    try:
        if method == "test":
            test(AdapterInstance.from_input()).send_results()
        elif method == "endpoint_urls":
            get_endpoints(AdapterInstance.from_input()).send_results()
        elif method == "collect":
            collect(AdapterInstance.from_input()).send_results()
        elif method == "adapter_definition":
            result = get_adapter_definition()
            if type(result) is AdapterDefinition:
                result.send_results()
            else:
                logger.info(
                    "get_adapter_definition method did not return an AdapterDefinition"
                )
                exit(1)
        else:
            logger.error(f"Command {method} not found")
            exit(1)
    finally:
        logger.info(Timer.graph())


if __name__ == "__main__":
    main(sys.argv[1:])
