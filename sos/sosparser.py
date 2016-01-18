# -*- coding: utf-8 -*-
"""
 SOS...Parser classes
 All classes to parse SOS or O&M XML data
"""

from PyQt4.QtCore import QVariant, Qt, QDateTime
from xmlparser import * #@UnusedWildImport
from gmlparser import * #@UnusedWildImport
from itertools import chain
from qgis.core import QgsOgcUtils as GMLParser, QgsRectangle, QgsField, QgsCoordinateReferenceSystem, QgsPoint, QgsGeometry
import sos
from qgstime import QgsTime


__all__ = ['XMLParserFactory',
           'SOSCapabilitiesParser',
           'SOSServiceIdentificationParser',
           'SOSServiceProviderParser',
           'SOSObservationOfferingParser',
           'SOSOperationMetadataParser',
           'SOSFilterCapabilitiesParser',
           'SOSObservationsParser']

class SOSCapabilitiesParser (XMLParser):
    def __init__(self):
        self.capabilities = sos.SOSCapabilities()

    def parse (self, xml):
        self.capabilities.xml = xml
    
        xml = XMLParser.parse(self, self.capabilities.xml)

        node, version = self.searchFirst (xml, "@version")
        if not node or not node.localName() == "Capabilities" or not version in ["1.0", "2.0.0"]:
            if node.localName() == "ExceptionReport":
                node, exceptionCode = self.searchFirst(node, "Exception@exceptionCode")
                _, exceptionText = self.searchFirst(node, "ExceptionText")
                raise sos.ExceptionReport (exceptionCode, exceptionText)
            raise ValueError ("{} version {}".format(node.localName(), version))
        
        self.capabilities.version = version
        for node, value in self.search (xml, "*"):
            if value == "ServiceIdentification":
                self.capabilities.serviceIdentification = XMLParserFactory.getInstance ("SOSServiceIdentification")().parse(node)
            elif value == "ServiceProvider":
                self.capabilities.serviceProvider = XMLParserFactory.getInstance ("SOSServiceProvider")().parse(node)
            elif value == "OperationsMetadata":
                opParser = XMLParserFactory.getInstance ("SOSOperationMetadata")
                for opNode, opName in self.search (node, "Operation@name"):
                    self.capabilities.operationsMetadata[str(opName)] = opParser().parse(opNode)
            elif value == "filterCapabilities":
                fcNode, _ = self.searchFirst(node, "Filter_Capabilities")
                if fcNode:
                    self.capabilities.filterCapabilities = XMLParserFactory.getInstance ("SOSFilterCapabilities")().parse(fcNode)
            elif value == "contents":
                contentsNode, _ = self.searchFirst(node, "Contents")
                ooParser = XMLParserFactory.getInstance ("SOSObservationOffering")
                for ooNode, _ in self.search (contentsNode, "offering/ObservationOffering"):
                    _, ooId = self.searchFirst(ooNode, "identifier")
                    self.capabilities.observationOfferingList[str(ooId)] = ooParser().parse(ooNode)
        return self.capabilities

class SOSServiceIdentificationParser (XMLParser):
    def __init__(self):
        self.identification = sos.SOSServiceIdentification ()

    def parse (self, xml):
        xml = XMLParser.parse(self, xml)

        _, self.identification.title = self.searchFirst (xml, "Title")
        _, self.identification.abstract = self.searchFirst (xml, "Abstract")
        for _, value in self.search (xml, "Keywords/Keyword"):
            self.identification.keywords.append(value)
        _, self.identification.serviceType = self.searchFirst (xml, "ServiceType")
        _, self.identification.serviceTypeVersion = self.searchFirst (xml, "ServiceTypeVersion")

        return self.identification

class SOSServiceProviderParser (XMLParser):
    def __init__(self):
        self.provider = sos.SOSServiceProvider ()

    def parse (self, xml):
        xml = XMLParser.parse(self, xml)

        _, self.provider.providerName = self.searchFirst (xml, "ProviderName")
        node, self.provider.providerSite = self.searchFirst (xml, "ProviderSite@href")
        contactInfo, value = self.searchFirst (xml, "ServiceContact/ContactInfo")
        for node, value in self.search (contactInfo, "Phone/*"):
            self.provider.phones[str(node.localName())] = value
        for node, value in self.search (contactInfo, "Address/*"):
            self.provider.address[str(node.localName())] = value

        return self.provider

class SOSObservationOfferingParser (XMLParser):
    def __init__(self):
        self.offering = sos.SOSObservationOffering ()

    def parse (self, xml):
        xml = XMLParser.parse(self, xml)

        _, self.offering.identifier = self.searchFirst (xml, "identifier")
        _, self.offering.procedure = self.searchFirst (xml, "procedure")
        for _, value in self.search (xml, "procedureDescriptionFormat"):
            self.offering.procedureDescriptionFormats.append(value)
        for _, value in self.search (xml, "observableProperty"):
            _, self.offering.observableProperties.append(value)
        
        observedAreaNode, observedAreaType = self.searchFirst (xml, "observedArea/*")
        if observedAreaNode:
            _, self.offering.srsName = self.searchFirst (observedAreaNode, "@srsName")
            if observedAreaType == "Envelope":
                self.offering.observedArea = GMLParser.rectangleFromGMLEnvelope(observedAreaNode)
            elif observedAreaType == "Box":
                self.offering.observedArea = GMLParser.rectangleFromGMLBox(observedAreaNode)
            else:
                geo = GMLParser.geometryFromGML(observedAreaNode)
                if geo:                
                    self.offering.observedArea = geo.boundingBox()
                else:
                    self.offering.observedArea = QgsRectangle()
        timeNode, timePrimitive = self.searchFirst (xml, "phenomenonTime/*")
        if timePrimitive:
            try:
                gmlTimeParser = XMLParserFactory.getInstance ("GML" + timePrimitive)
                self.offering.phenomenonTime = gmlTimeParser().parse(timeNode)
            except NotImplementedError:
                self.offering.phenomenonTime = QgsTime()
                
        resultTimeNode, resultTimePrimitive = self.searchFirst (xml, "resultTime/*")
        if resultTimePrimitive:
            try:
                gmlTimeParser = XMLParserFactory.getInstance ("GML" + resultTimePrimitive)
                self.offering.resultTime = gmlTimeParser().parse(resultTimeNode)
            except NotImplementedError:
                self.offering.resultTime = QgsTime()
        
        _, self.offering.featureOfInterestType = self.searchFirst (xml, "featureOfInterestType")

        for _, value in self.search (xml, "responseFormat"):
            self.offering.responseFormats.append(value)
        
        for _, value in self.search (xml, "observationType"):  
            _, self.offering.observationTypes.append(value)

        return self.offering

class SOSOperationMetadataParser (XMLParser):
    def __init__(self):
        self.operation = sos.SOSOperationMetadata()

    def parse (self, xml):
        xml = XMLParser.parse(self, xml)

        _, self.operation.name = self.searchFirst (xml, "name")
        methods = []
        for node, name in self.search(xml, "DCP/HTTP/*"):
            _, href = self.searchFirst(node, "@href")
            constrainNode,_ = self.searchFirst (node, 'Constraint@name=Content-Type')
            if constrainNode:
                for _, contentType in self.search(constrainNode, 'AllowedValues/Value'):
                    if contentType in ['application/xml','text/xml']:
                        methods.append((name,href))
                        break
            else:
                methods.append((name,href))
        self.operation.methods = dict(methods)
        
        parameters = []
        for node, name in self.search(xml, "Parameter@name"):
            parameters.append((name,[val for _,val in self.search(node, "AllowedValues/Value")]))
        self.operation.parameters = dict(parameters)
        
        return self.operation
    
class SOSFilterCapabilitiesParser (XMLParser):
    def __init__(self):
        self.capabilities = sos.SOSFilterCapabilities ()

    def parse (self, xml):
        xml = XMLParser.parse(self, xml)
        
        # Spatial_Capabilities
        self.capabilities.spatial_operands = [op for _, op in self.search(xml, "Spatial_Capabilities/GeometryOperands/GeometryOperand")]
        self.capabilities.spatial_operators = [op for _, op in self.search(xml, "Spatial_Capabilities/SpatialOperators/SpatialOperator@name")]
        
        # Temporal_Capabilities
        self.capabilities.temporal_operands = [op for _, op in self.search(xml, "Temporal_Capabilities/TemporalOperands/TemporalOperand")]
        self.capabilities.temporal_operators = [op for _, op in self.search(xml, "Temporal_Capabilities/TemporalOperators/TemporalOperator@name")]
        
        # Scalar_Capabilities
        self.capabilities.scalar_operators = [op for _,op in self.search(xml, "Scalar_Capabilities/ComparisonOperators/ComparisonOperator")]
        
        return self.capabilities
    
class SOSObservationsParser (XMLParser):
    def __init__(self):
        self.provider = sos.SOSProvider()
        
    def parse (self, xml):
        xml = XMLParser.parse(self, xml)
        node,_ = self.searchFirst (xml, "")        
        if not node or not node.localName() == "ObservationCollection":
            if node.localName() == "ExceptionReport":
                node, exceptionCode = self.searchFirst(node, "Exception@exceptionCode")
                _, exceptionText = self.searchFirst(node, "ExceptionText")
                raise sos.ExceptionReport (exceptionCode, exceptionText)
            raise ValueError (node.localName())
        
        boundedByNode, boundedByType = self.searchFirst (xml, "boundedBy/*")
        _, self.provider.srsName = self.searchFirst (boundedByNode, "@srsName")
        crs = QgsCoordinateReferenceSystem()
        if crs.createFromUserInput(self.provider.srsName):
            yx = crs.axisInverted()
        else:
            yx = (self.provider.srsName == 'urn:ogc:def:crs:EPSG:0') #Hack para meteogalicia
            
        if boundedByType == "Envelope":
            self.provider.extent = GMLParser.rectangleFromGMLEnvelope(boundedByNode)
        elif boundedByType == "Box":
            self.provider.extent = GMLParser.rectangleFromGMLBox(boundedByNode)
        else:
            geo = GMLParser.geometryFromGML(boundedByNode)
            if geo:                
                self.provider.extent = geo.boundingBox()
        
        _, tag = self.searchFirst(xml, 'member/*')
        omParser = XMLParserFactory.getInstance(tag)(self.provider, yx)
        
        components = omParser.parse(xml) 
                                    
        components = filter(lambda f: f != None, components.values())
        hasTime = False
        for i, f in enumerate(components):
            if f.name() == "Time" or f.name() == "SamplingTime":
                components.pop (i)
                f.setName("Time")
                self.provider.fields.append(f)
                hasTime = True
                break
        if not hasTime:
            self.provider.fields.append(QgsField ("Time", QVariant.String, ''))
        self.provider.fields.extend(components)
           
        return self.provider
    
class ObservationParser (XMLParser):
    def __init__(self, provider, axisInverted):
        self.provider = provider
        self.yx = axisInverted
        self.timeParser = XMLParserFactory.getInstance ("GMLTime")()

    def parse (self, xml):
        def _float (value):
            try: return float(value)
            except: return None
        
        components = {}
        for member, _ in self.search(xml, "member"):
            for node, tag in self.search (member, "Observation/*"):
                if tag == "samplingTime":
                    samplingTime = self.timeParser.parse(node)
                elif tag == "observedProperty":
                    _, prop = self.searchFirst(node, "@href")
                    if prop:
                        if not prop in components: components[prop] = None
                    else:
                        for _, prop in self.search (node, "CompositePhenomenon/component@href"):
                            if not prop in components: components[prop] = None
                elif tag == "featureOfInterest":
                    hasSamplingPoint = False
                    for point, foi_id in chain(self.search (node, "FeatureCollection/featureMember/SamplingPoint@id"),self.search (node, "SamplingPoint@id"),self.search (node, "SamplingPointAtDepth@id")):
                        hasSamplingPoint = True
                        _, name = self.searchFirst (point, "name")
                        pointGeo, _ = self.searchFirst(point, "position")
                        pointGeo = GMLParser.geometryFromGML(pointGeo)
                        if self.yx:
                            pointGeo = pointGeo.asPoint()
                            pointGeo = QgsGeometry.fromPoint(QgsPoint (pointGeo.y(),pointGeo.x()))
                        self.provider.features [foi_id] = (name, pointGeo)
                        if point.localName () == "SamplingPointAtDepth":
                            _, depth = self.searchFirst (point, "depth")
                            foi_id = (foi_id, depth)
                    if not hasSamplingPoint:
                        for _, foi_id in self.search (node, "FeatureCollection/featureMember@href"):
                            self.provider.features [foi_id] = (foi_id, None)
                elif tag == "result":
                    node, tag = self.searchFirst(node, "*")
                    if tag == "DataArray":
                        simpleDataRecord = []
                        for fieldNode, field in chain(self.search(node, "elementType/SimpleDataRecord/field@name"),self.search(node, "elementType/DataRecord/field@name")):
                            simpleDataRecord.append(field)
                            fieldNode, definition = self.searchFirst(fieldNode, "*/@definition")
                            if definition in components and components[definition] == None:
                                if fieldNode.localName () == "Quantity":
                                    fieldType = QVariant.Double
                                    _, definition = self.searchFirst (fieldNode, "uom@code")
                                elif fieldNode.localName () == "Time":
                                    fieldType = QVariant.String
                                else:
                                    fieldType = QVariant.String
                                components[definition] = QgsField (field, fieldType, definition)
                        
                        encoding, _ = self.searchFirst (node, "encoding")
                        _, blockSeparator = self.searchFirst (encoding, "TextBlock@blockSeparator")
                        _, tokenSeparator = self.searchFirst (encoding, "TextBlock@tokenSeparator")
                        _, values = self.searchFirst (node, "values")
                        try:
                            indexes = map(simpleDataRecord.index, ["feature", "Time"])
                        except:
                            indexes = None
                        
                        if not indexes:
                            try:
                                indexes = map(simpleDataRecord.index, ["FeatureOfInterest","SamplingTime"])
                            except:
                                indexes = None
                                
                        if not indexes:
                            raise ValueError('SimpleDataRecord = ' + str(simpleDataRecord)) 

                        map(simpleDataRecord.pop, indexes)
                        for block in filter (lambda x: len(x), values.split (blockSeparator)):
                            observation = block.split(tokenSeparator)
                            observationKeys = map(observation.pop, indexes)
                            map (lambda prop, value: self.provider.setObservation (unicode(observationKeys[0]), QDateTime.fromString(observationKeys[1], Qt.ISODate), unicode(prop), str(value)), simpleDataRecord, observation)
        return components                        
        
class MeasurementParser (XMLParser):
    def __init__(self, provider, axisInverted):
        self.provider = provider
        self.yx = axisInverted
        self.timeParser = XMLParserFactory.getInstance ("GMLTime")()

    def parse (self, xml):
        def _float (value):
            try: return float(value)
            except: return None
        
        components = {}
        for member, _ in self.search(xml, "member"):
            for node, tag in self.search (member, "Measurement/*"):
                if tag == "samplingTime":
                    samplingTime = self.timeParser.parse(node)
                elif tag == "observedProperty":
                    _, prop = self.searchFirst(node, "@href")
                    if not prop in components: components[prop] = None
                elif tag == "featureOfInterest":
                    hasSamplingPoint = False
                    for point, foi_id in chain(self.search (node, "FeatureCollection/featureMember/SamplingPoint@id"),self.search (node, "SamplingPoint@id"),self.search (node, "SamplingPointAtDepth@id")):
                        hasSamplingPoint = True
                        _, name = self.searchFirst (point, "name")
                        pointGeo, _ = self.searchFirst(point, "position")
                        pointGeo = GMLParser.geometryFromGML(pointGeo)
                        if self.yx:
                            pointGeo = pointGeo.asPoint()
                            pointGeo = QgsGeometry.fromPoint(QgsPoint (pointGeo.y(),pointGeo.x()))
                        self.provider.features [foi_id] = (name, pointGeo)
                        if point.localName () == "SamplingPointAtDepth":
                            _, depth = self.searchFirst (point, "depth")
                            foi_id = (foi_id, depth)
                    if not hasSamplingPoint:
                        for _, foi_id in self.search (node, "FeatureCollection/featureMember@href"):
                            self.provider.features [foi_id] = (foi_id, None)
                elif node.localName () == "result":
                    self.provider.setObservation (unicode(foi_id), QDateTime.fromString(str(samplingTime), Qt.ISODate), unicode(prop), str(tag))
                    if prop in components and components[prop] == None:
                        components[prop] = QgsField (prop, QVariant.Double if _float(tag) else QVariant.String, node.attribute("uom"))
        return components                        