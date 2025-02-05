from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union
from uuid import uuid4

from pycrdt import Array, Doc, Map
from pydantic import BaseModel
from ypywidgets.comm import CommWidget

from .objects import (
    IGeoJSONSource,
    IGeoTiffSource,
    IHeatmapLayer,
    IHillshadeLayer,
    IImageLayer,
    IImageSource,
    IRasterDemSource,
    IRasterLayer,
    IRasterSource,
    IVectorLayer,
    IVectorTileLayer,
    IVectorTileSource,
    IVideoSource,
    IWebGlLayer,
    LayerType,
    SourceType,
)
from .utils import normalize_path

logger = logging.getLogger(__file__)


def reversed_tree(root):
    if isinstance(root, list):
        return reversed([reversed_tree(el) for el in root])
    return root


class GISDocument(CommWidget):
    """
    Create a new GISDocument object.

    :param path: the path to the file that you would like to open.
    If not provided, a new empty document will be created.
    """

    def __init__(
        self,
        path: Optional[str | Path] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        zoom: Optional[float] = None,
        extent: Optional[List[float]] = None,
        bearing: Optional[float] = None,
        pitch: Optional[float] = None,
        projection: Optional[str] = None,
    ):
        if isinstance(path, Path):
            path = str(path)

        comm_metadata = GISDocument._path_to_comm(path)

        # Create an empty project file if it does not exist
        if comm_metadata["path"] and not os.path.isfile(comm_metadata["path"]):
            with open(comm_metadata["path"], "w") as fd:
                fd.write("{}")

        ydoc = Doc()

        super().__init__(
            comm_metadata=dict(ymodel_name="@jupytergis:widget", **comm_metadata),
            ydoc=ydoc,
        )

        self.ydoc["layers"] = self._layers = Map()
        self.ydoc["sources"] = self._sources = Map()
        self.ydoc["options"] = self._options = Map()
        self.ydoc["layerTree"] = self._layerTree = Array()
        self.ydoc["metadata"] = self._metadata = Map()

        if path is None:
            if latitude is not None:
                self._options["latitude"] = latitude
            if longitude is not None:
                self._options["longitude"] = longitude
            if extent is not None:
                self._options["extent"] = extent
            if zoom is not None:
                self._options["zoom"] = zoom
            if bearing is not None:
                self._options["bearing"] = bearing
            if pitch is not None:
                self._options["pitch"] = pitch
            if projection is not None:
                self._options["projection"] = projection

    @property
    def layers(self) -> Dict:
        """
        Get the layer list
        """
        return self._layers.to_py()

    @property
    def layer_tree(self) -> List[str | Dict]:
        """
        Get the layer tree
        """
        return self._layerTree.to_py()

    def export_to_qgis(self, path: str | Path) -> bool:
        # Lazy import, jupytergis_qgis of qgis may not be installed
        from jupytergis_qgis.qgis_loader import export_project_to_qgis

        if isinstance(path, Path):
            path = str(path)

        virtual_file = {
            "layers": self._layers.to_py(),
            "sources": self._sources.to_py(),
            "layerTree": reversed_tree(self._layerTree.to_py()),
            "options": self._options.to_py(),
        }
        return export_project_to_qgis(path, virtual_file)

    def add_raster_layer(
        self,
        url: str,
        name: str = "Raster Layer",
        attribution: str = "",
        opacity: float = 1,
    ):
        """
        Add a Raster Layer to the document.

        :param name: The name that will be used for the object in the document.
        :param url: The tiles url.
        :param attribution: The attribution.
        :param opacity: The opacity, between 0 and 1.
        """
        source = {
            "type": SourceType.RasterSource,
            "name": f"{name} Source",
            "parameters": {
                "url": url,
                "minZoom": 0,
                "maxZoom": 24,
                "attribution": attribution,
                "htmlAttribution": attribution,
                "provider": "",
                "bounds": [],
                "urlParameters": {},
            },
        }

        source_id = self._add_source(OBJECT_FACTORY.create_source(source, self))

        layer = {
            "type": LayerType.RasterLayer,
            "name": name,
            "visible": True,
            "parameters": {"source": source_id, "opacity": opacity},
        }

        return self._add_layer(OBJECT_FACTORY.create_layer(layer, self))

    def add_vectortile_layer(
        self,
        url: str,
        name: str = "Vector Tile Layer",
        attribution: str = "",
        min_zoom: int = 0,
        max_zoom: int = 24,
        type: Literal["circle", "fill", "line"] = "line",
        color_expr=None,
        opacity: float = 1,
        logical_op: str | None = None,
        feature: str | None = None,
        operator: str | None = None,
        value: Union[str, float, float] | None = None,
    ):
        """
        Add a Vector Tile Layer to the document.

        :param name: The name that will be used for the object in the document.
        :param url: The tiles url.
        :param attribution: The attribution.
        :param opacity: The opacity, between 0 and 1.
        """

        source = {
            "type": SourceType.VectorTileSource,
            "name": f"{name} Source",
            "parameters": {
                "url": url,
                "minZoom": min_zoom,
                "maxZoom": max_zoom,
                "attribution": attribution,
                "htmlAttribution": attribution,
                "provider": "",
                "bounds": [],
                "urlParameters": {},
            },
        }

        source_id = self._add_source(OBJECT_FACTORY.create_source(source, self))

        layer = {
            "type": LayerType.VectorTileLayer,
            "name": name,
            "visible": True,
            "parameters": {
                "source": source_id,
                "type": type,
                "opacity": opacity,
                "color": color_expr,
                "opacity": opacity,
            },
            "filters": {
                "appliedFilters": [
                    {"feature": feature, "operator": operator, "value": value}
                ],
                "logicalOp": logical_op,
            },
        }

        return self._add_layer(OBJECT_FACTORY.create_layer(layer, self))

    def add_geojson_layer(
        self,
        path: str | Path | None = None,
        data: Dict | None = None,
        name: str = "GeoJSON Layer",
        type: "circle" | "fill" | "line" = "line",
        opacity: float = 1,
        logical_op: str | None = None,
        feature: str | None = None,
        operator: str | None = None,
        value: Union[str, number, float] | None = None,
        color_expr=None,
    ):
        """
        Add a GeoJSON Layer to the document.

        :param name: The name that will be used for the object in the document.
        :param path: The path to the JSON file to embed into the jGIS file.
        :param data: The raw GeoJSON data to embed into the jGIS file.
        :param type: The type of the vector layer to create.
        :param color: The color to apply to features.
        :param opacity: The opacity, between 0 and 1.
        :param color_expr: The style expression used to style the layer, defaults to None
        """
        if isinstance(path, Path):
            path = str(path)

        if path is None and data is None:
            raise ValueError("Cannot create a GeoJSON layer without data")

        if path is not None and data is not None:
            raise ValueError("Cannot set GeoJSON layer data and path at the same time")

        if path is not None:
            # We cannot put the path to the file in the model
            # We don't know where the kernel runs/live
            # The front-end would have no way of finding the file reliably
            # TODO Support urls to JSON files, in that case, don't embed the data
            with open(path, "r") as fobj:
                parameters = {"data": json.loads(fobj.read())}

        if data is not None:
            parameters = {"data": data}

        source = {
            "type": SourceType.GeoJSONSource,
            "name": f"{name} Source",
            "parameters": parameters,
        }

        source_id = self._add_source(OBJECT_FACTORY.create_source(source, self))

        layer = {
            "type": LayerType.VectorLayer,
            "name": name,
            "visible": True,
            "parameters": {
                "source": source_id,
                "type": type,
                "color": color_expr,
                "opacity": opacity,
            },
            "filters": {
                "appliedFilters": [
                    {"feature": feature, "operator": operator, "value": value}
                ],
                "logicalOp": logical_op,
            },
        }

        return self._add_layer(OBJECT_FACTORY.create_layer(layer, self))

    def add_vector_layer(
        self,
        path: Optional[Union[str, Path]] = None,
        name: str = "Vector Layer",
        type: str = "line",
        opacity: float = 1.0,
        logical_op: Optional[str] = None,
        feature: Optional[str] = None,
        operator: Optional[str] = None,
        value: Optional[Union[str, int, float]] = None,
        color_expr: Optional[str] = None,
        **kwargs,
    ) -> None:
        """
        Adds a vector layer to the map.

        Args:
            path (Optional[Union[str, Path]]): The path to the vector file.
            name (str): The name of the vector layer. Defaults to "Vector Layer".
            type (str): The type of the vector layer. Defaults to "line".
            opacity (float): The opacity of the vector layer. Defaults to 1.0.
            logical_op (Optional[str]): The logical operation to apply. Defaults to None.
            feature (Optional[str]): The feature to apply the logical operation on. Defaults to None.
            operator (Optional[str]): The operator to use in the logical operation. Defaults to None.
            value (Optional[Union[str, int, float]]): The value to use in the logical operation. Defaults to None.
            color_expr (Optional[str]): The color expression to use for the vector layer. Defaults to None.
            **kwargs: Additional keyword arguments.

        Returns:
            None
        """
        geojson = vector_to_geojson(path, **kwargs)
        self.add_geojson_layer(
            data=geojson,
            name=name,
            type=type,
            opacity=opacity,
            logical_op=logical_op,
            feature=feature,
            operator=operator,
            value=value,
            color_expr=color_expr,
        )

    def add_image_layer(
        self,
        url: str,
        coordinates: [],
        name: str = "Image Layer",
        opacity: float = 1,
    ):
        """
        Add a Image Layer to the document.

        :param name: The name that will be used for the object in the document.
        :param url: The image url.
        :param coordinates: Corners of image specified in longitude, latitude pairs.
        :param opacity: The opacity, between 0 and 1.
        """

        if url is None or coordinates is None:
            raise ValueError("URL and Coordinates are required")

        source = {
            "type": SourceType.ImageSource,
            "name": f"{name} Source",
            "parameters": {"path": url, "coordinates": coordinates},
        }

        source_id = self._add_source(OBJECT_FACTORY.create_source(source, self))

        layer = {
            "type": LayerType.ImageLayer,
            "name": name,
            "visible": True,
            "parameters": {"source": source_id, "opacity": opacity},
        }

        return self._add_layer(OBJECT_FACTORY.create_layer(layer, self))

    def add_video_layer(
        self,
        urls: [],
        name: str = "Image Layer",
        coordinates: [] = [],
        opacity: float = 1,
    ):
        """
        Add a Video Layer to the document.

        :param name: The name that will be used for the object in the document.
        :param urls: URLs to video content in order of preferred format.
        :param coordinates: Corners of video specified in longitude, latitude pairs.
        :param opacity: The opacity, between 0 and 1.
        """

        if urls is None or coordinates is None:
            raise ValueError("URLs and Coordinates are required")

        source = {
            "type": SourceType.VideoSource,
            "name": f"{name} Source",
            "parameters": {"urls": urls, "coordinates": coordinates},
        }

        source_id = self._add_source(OBJECT_FACTORY.create_source(source, self))

        layer = {
            "type": LayerType.RasterLayer,
            "name": name,
            "visible": True,
            "parameters": {"source": source_id, "opacity": opacity},
        }

        return self._add_layer(OBJECT_FACTORY.create_layer(layer, self))

    def add_tiff_layer(
        self,
        url: str,
        min: int = None,
        max: int = None,
        name: str = "Tiff Layer",
        normalize: bool = True,
        wrapX: bool = False,
        attribution: str = "",
        opacity: float = 1.0,
        color_expr=None,
    ):
        """
        Add a tiff layer

        :param str url: URL of the tif
        :param int min: Minimum pixel value to be displayed, defaults to letting the map display set the value
        :param int max: Maximum pixel value to be displayed, defaults to letting the map display set the value
        :param str name: The name that will be used for the object in the document, defaults to "Tiff Layer"
        :param bool normalize: Select whether to normalize values between 0..1, if false than min/max have no effect, defaults to True
        :param bool wrapX: Render tiles beyond the tile grid extent, defaults to False
        :param float opacity: The opacity, between 0 and 1, defaults to 1.0
        :param _type_ color_expr: The style expression used to style the layer, defaults to None
        """

        source = {
            "type": SourceType.GeoTiffSource,
            "name": f"{name} Source",
            "parameters": {
                "urls": [{"url": url, "min": min, "max": max}],
                "normalize": normalize,
                "wrapX": wrapX,
            },
        }
        source_id = self._add_source(OBJECT_FACTORY.create_source(source, self))

        layer = {
            "type": LayerType.WebGlLayer,
            "name": name,
            "visible": True,
            "parameters": {
                "source": source_id,
                "opacity": opacity,
                "color": color_expr,
            },
        }

        return self._add_layer(OBJECT_FACTORY.create_layer(layer, self))

    def add_hillshade_layer(
        self,
        url: str,
        name: str = "Hillshade Layer",
        urlParameters: Dict = {},
        attribution: str = "",
    ):
        """
        Add a hillshade layer

        :param str url: URL of the hillshade layer
        :param str name: The name that will be used for the object in the document, defaults to "Hillshade Layer"
        :param attribution: The attribution.
        """

        source = {
            "type": SourceType.RasterDemSource,
            "name": f"{name} Source",
            "parameters": {
                "url": url,
                "attribution": attribution,
                "urlParameters": urlParameters,
            },
        }
        source_id = self._add_source(OBJECT_FACTORY.create_source(source, self))

        layer = {
            "type": LayerType.HillshadeLayer,
            "name": name,
            "visible": True,
            "parameters": {"source": source_id},
        }

        return self._add_layer(OBJECT_FACTORY.create_layer(layer, self))

    def add_heatmap_layer(
        self,
        feature: string,
        path: str | Path | None = None,
        data: Dict | None = None,
        name: str = "Heatmap Layer",
        opacity: float = 1,
        blur: number = 15,
        radius: number = 8,
        gradient: List[str] = ["#00f", "#0ff", "#0f0", "#ff0", "#f00"],
    ):
        """
        Add a Heatmap Layer to the document.

        :param name: The name that will be used for the object in the document.
        :param path: The path to the JSON file to embed into the jGIS file.
        :param data: The raw GeoJSON data to embed into the jGIS file.
        :param gradient: The color gradient to apply.
        :param opacity: The opacity, between 0 and 1.
        :param blur: The blur size in pixels
        :param radius: The radius size in pixels
        :param feature: The feature to use to heatmap weights
        """
        if isinstance(path, Path):
            path = str(path)

        if path is None and data is None:
            raise ValueError("Cannot create a GeoJSON source without data")

        if path is not None and data is not None:
            raise ValueError("Cannot set GeoJSON source data and path at the same time")

        if path is not None:
            # We cannot put the path to the file in the model
            # We don't know where the kernel runs/live
            # The front-end would have no way of finding the file reliably
            # TODO Support urls to JSON files, in that case, don't embed the data
            with open(path, "r") as fobj:
                parameters = {"data": json.loads(fobj.read())}

        if data is not None:
            parameters = {"data": data}

        source = {
            "type": SourceType.GeoJSONSource,
            "name": f"{name} Source",
            "parameters": parameters,
        }

        source_id = self._add_source(OBJECT_FACTORY.create_source(source, self))

        layer = {
            "type": LayerType.HeatmapLayer,
            "name": name,
            "visible": True,
            "parameters": {
                "source": source_id,
                "type": type,
                "color": gradient,
                "opacity": opacity,
                "blur": blur,
                "radius": radius,
                "feature": feature,
            },
        }

        return self._add_layer(OBJECT_FACTORY.create_layer(layer, self))

    def create_color_expr(
        self,
        color_stops: Dict,
        band: float = 1.0,
        interpolation_type: str = "linear",
    ):
        """
        Create a color expression used to style the layer

        :param Dict color_stops: Dictionary of stop values to [r, g, b, a] colors
        :param float band: The band to be colored, defaults to 1.0
        :param str interpolation_type: The interpolation function. Can be linear, discrete, or exact, defaults to 'linear'
        """

        if interpolation_type not in ["linear", "discrete", "exact"]:
            raise ValueError(
                "Interpolation type must be one of linear, discrete, or exact"
            )

        color = []
        if interpolation_type == "linear":
            color = ["interpolate", ["linear"]]
            color.append(["band", band])
            # Transparency for nodata
            color.append(0.0)
            color.append([0.0, 0.0, 0.0, 0.0])

            for value, colorVal in color_stops.items():
                color.append(value)
                color.append(colorVal)

            return color

        if interpolation_type == "discrete":
            operator = "<="

        if interpolation_type == "exact":
            operator = "=="

        color = ["case"]
        # Transparency for nodata
        color.append(["==", ["band", band], 0.0])
        color.append([0.0, 0.0, 0.0, 0.0])

        for value, colorVal in color_stops.items():
            color.append([operator, ["band", band], value])
            color.append(colorVal)

        # Fallback color
        color.append([0.0, 0.0, 0.0, 1.0])

        return color

    def add_filter(
        self,
        layer_id: str,
        logical_op: str,
        feature: str,
        operator: str,
        value: Union[str, number, float],
    ):
        """
        Add a filter to a layer

        :param str layer_id: The ID of the layer to filter
        :param str logical_op: The logical combination to apply to filters. Must be "any" or "all"
        :param str feature: The feature to be filtered on
        :param str operator: The operator used to compare the feature and value
        :param Union[str, number, float] value: The value to be filtered on
        """
        layer = self._layers.get(layer_id)

        # Check if the layer exists
        if layer is None:
            raise ValueError(f"No layer found with ID: {layer_id}")

        # Initialize filters if it doesn't exist
        if "filters" not in layer:
            layer["filters"] = {
                "appliedFilters": [
                    {"feature": feature, "operator": operator, "value": value}
                ],
                "logicalOp": logical_op,
            }

            self._layers[layer_id] = layer
            return

        # Add new filter
        filters = layer["filters"]
        filters["appliedFilters"].append(
            {"feature": feature, "operator": operator, "value": value}
        )

        # update the logical operation
        filters["logicalOp"] = logical_op

        self._layers[layer_id] = layer

    def update_filter(
        self,
        layer_id: str,
        logical_op: str,
        feature: str,
        operator: str,
        value: Union[str, number, float],
    ):
        """
        Update a filter applied to a layer

        :param str layer_id: The ID of the layer to filter
        :param str logical_op: The logical combination to apply to filters. Must be "any" or "all"
        :param str feature: The feature to update the value for
        :param str operator: The operator used to compare the feature and value
        :param Union[str, number, float] value: The new value to be filtered on
        """
        layer = self._layers.get(layer_id)

        # Check if the layer exists
        if layer is None:
            raise ValueError(f"No layer found with ID: {layer_id}")

        if "filters" not in layer:
            raise ValueError(f"No filters applied to layer: {layer_id}")

        # Find the feature within the layer
        feature = next(
            (f for f in layer["filters"]["appliedFilters"] if f["feature"] == feature),
            None,
        )
        if feature is None:
            raise ValueError(
                f"No feature found with ID: {feature} in layer: {layer_id}"
            )
            return

        # Update the feature value
        feature["value"] = value

        # update the logical operation
        layer["filters"]["logicalOp"] = logical_op

        self._layers[layer_id] = layer

    def clear_filters(self, layer_id: str):
        """
        Clear filters on a layer

        :param str layer_id: The ID of the layer to clear filters from
        """
        layer = self._layers.get(layer_id)

        # Check if the layer exists
        if layer is None:
            raise ValueError(f"No layer found with ID: {layer_id}")

        if "filters" not in layer:
            raise ValueError(f"No filters applied to layer: {layer_id}")

        layer["filters"]["appliedFilters"] = []
        self._layers[layer_id] = layer

    def _add_source(self, new_object: "JGISObject"):
        _id = str(uuid4())
        obj_dict = json.loads(new_object.json())
        self._sources[_id] = obj_dict
        return _id

    def _add_layer(self, new_object: "JGISObject"):
        _id = str(uuid4())
        obj_dict = json.loads(new_object.json())
        self._layers[_id] = obj_dict
        self._layerTree.append(_id)
        return _id

    @classmethod
    def _path_to_comm(cls, filePath: Optional[str]) -> Dict:
        path = None
        format = None
        contentType = None

        if filePath is not None:
            path = normalize_path(filePath)
            file_name = Path(path).name
            try:
                ext = file_name.split(".")[1].lower()
            except Exception:
                raise ValueError("Can not detect file extension!")
            if ext == "jgis":
                format = "text"
                contentType = "jgis"
            elif ext == "qgz":
                format = "base64"
                contentType = "QGZ"
            elif ext == "qgs":
                format = "base64"
                contentType = "QGS"
            else:
                raise ValueError("File extension is not supported!")
        return dict(
            path=path, format=format, contentType=contentType, createydoc=path is None
        )


class JGISLayer(BaseModel):
    class Config:
        arbitrary_types_allowed = True
        extra = "allow"

    name: str
    type: LayerType
    visible: bool
    parameters: Union[
        IRasterLayer,
        IVectorLayer,
        IVectorTileLayer,
        IHillshadeLayer,
        IImageLayer,
        IWebGlLayer,
        IHeatmapLayer,
    ]
    _parent = Optional[GISDocument]

    def __init__(__pydantic_self__, parent, **data: Any) -> None:  # noqa
        super().__init__(**data)
        __pydantic_self__._parent = parent


class JGISSource(BaseModel):
    class Config:
        arbitrary_types_allowed = True
        extra = "allow"

    name: str
    type: SourceType
    parameters: Union[
        IRasterSource,
        IVectorTileSource,
        IGeoJSONSource,
        IImageSource,
        IVideoSource,
        IGeoTiffSource,
        IRasterDemSource,
    ]
    _parent = Optional[GISDocument]

    def __init__(__pydantic_self__, parent, **data: Any) -> None:  # noqa
        super().__init__(**data)
        __pydantic_self__._parent = parent


class SingletonMeta(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            instance = super().__call__(*args, **kwargs)
            cls._instances[cls] = instance
        return cls._instances[cls]


class ObjectFactoryManager(metaclass=SingletonMeta):
    def __init__(self):
        self._factories: Dict[str, type[BaseModel]] = {}

    def register_factory(self, shape_type: str, cls: type[BaseModel]) -> None:
        if shape_type not in self._factories:
            self._factories[shape_type] = cls

    def create_layer(
        self, data: Dict, parent: Optional[GISDocument] = None
    ) -> Optional[JGISLayer]:
        object_type = data.get("type", None)
        name: str = data.get("name", None)
        visible: str = data.get("visible", True)
        filters = data.get("filters", None)
        if object_type and object_type in self._factories:
            Model = self._factories[object_type]
            args = {}
            params = data["parameters"]
            for field in Model.__fields__:
                args[field] = params.get(field, None)
            obj_params = Model(**args)
            return JGISLayer(
                parent=parent,
                name=name,
                visible=visible,
                type=object_type,
                parameters=obj_params,
                filters=filters,
            )

        return None

    def create_source(
        self, data: Dict, parent: Optional[GISDocument] = None
    ) -> Optional[JGISSource]:
        object_type = data.get("type", None)
        name: str = data.get("name", None)
        if object_type and object_type in self._factories:
            Model = self._factories[object_type]
            args = {}
            params = data["parameters"]
            for field in Model.__fields__:
                args[field] = params.get(field, None)
            obj_params = Model(**args)
            return JGISSource(
                parent=parent, name=name, type=object_type, parameters=obj_params
            )

        return None


def vector_to_geojson(
    filepath,
    out_geojson=None,
    bbox=None,
    mask=None,
    rows=None,
    epsg="4326",
    encoding="utf-8",
    **kwargs,
):
    """Converts any geopandas-supported vector dataset to GeoJSON.

    Args:
        filepath (str): Either the absolute or relative path to the file or URL
            to be opened, or any object with a read() method (such as an open
            file or StringIO).
        out_geojson (str, optional): The file path to the output GeoJSON.
            Defaults to None.
        bbox (tuple | GeoDataFrame or GeoSeries | shapely Geometry, optional):
            Filter features by given bounding box, GeoSeries, GeoDataFrame or
            a shapely geometry. CRS mis-matches are resolved if given a GeoSeries
            or GeoDataFrame. Cannot be used with mask. Defaults to None.
        mask (dict | GeoDataFrame or GeoSeries | shapely Geometry, optional):
            Filter for features that intersect with the given dict-like geojson
            geometry, GeoSeries, GeoDataFrame or shapely geometry. CRS mis-matches
            are resolved if given a GeoSeries or GeoDataFrame. Cannot be used with
            bbox. Defaults to None.
        rows (int or slice, optional): Load in specific rows by passing an integer
            (first n rows) or a slice() object.. Defaults to None.
        epsg (str, optional): The EPSG number to convert to. Defaults to "4326".
        encoding (str, optional): The encoding of the input file. Defaults to "utf-8".
        kwargs: Additional arguments to pass to geopandas.read_file.


    Raises:
        ValueError: When the output file path is invalid.

    Returns:
        dict: A dictionary containing the GeoJSON.
    """

    try:
        import geopandas as gpd
    except ImportError:
        raise ImportError(
            "geopandas is required for this function. Please install it using `pip install geopandas`."
        )

    if not filepath.startswith("http"):
        filepath = os.path.abspath(filepath)
        if filepath.endswith(".zip"):
            filepath = "zip://" + filepath
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".kml":

        try:
            import fiona
        except ImportError:
            raise ImportError(
                "fiona is required for this function. Please install it using `pip install fiona`."
            )

        fiona.drvsupport.supported_drivers["KML"] = "rw"
        df = gpd.read_file(
            filepath,
            bbox=bbox,
            mask=mask,
            rows=rows,
            driver="KML",
            encoding=encoding,
            **kwargs,
        )
    else:
        df = gpd.read_file(
            filepath, bbox=bbox, mask=mask, rows=rows, encoding=encoding, **kwargs
        )
    gdf = df.to_crs(epsg=epsg)

    if out_geojson is not None:
        if not out_geojson.lower().endswith(".geojson"):
            raise ValueError("The output file must have a geojson file extension.")

        out_geojson = os.path.abspath(out_geojson)
        out_dir = os.path.dirname(out_geojson)
        if not os.path.exists(out_dir):
            os.makedirs(out_dir)

        gdf.to_file(out_geojson, driver="GeoJSON")

    else:
        return gdf.__geo_interface__


OBJECT_FACTORY = ObjectFactoryManager()

OBJECT_FACTORY.register_factory(LayerType.RasterLayer, IRasterLayer)
OBJECT_FACTORY.register_factory(LayerType.VectorLayer, IVectorLayer)
OBJECT_FACTORY.register_factory(LayerType.VectorTileLayer, IVectorTileLayer)
OBJECT_FACTORY.register_factory(LayerType.HillshadeLayer, IHillshadeLayer)
OBJECT_FACTORY.register_factory(LayerType.WebGlLayer, IWebGlLayer)
OBJECT_FACTORY.register_factory(LayerType.ImageLayer, IImageLayer)
OBJECT_FACTORY.register_factory(LayerType.HeatmapLayer, IHeatmapLayer)

OBJECT_FACTORY.register_factory(SourceType.VectorTileSource, IVectorTileSource)
OBJECT_FACTORY.register_factory(SourceType.RasterSource, IRasterSource)
OBJECT_FACTORY.register_factory(SourceType.GeoJSONSource, IGeoJSONSource)
OBJECT_FACTORY.register_factory(SourceType.ImageSource, IImageSource)
OBJECT_FACTORY.register_factory(SourceType.VideoSource, IVideoSource)
OBJECT_FACTORY.register_factory(SourceType.GeoTiffSource, IGeoTiffSource)
OBJECT_FACTORY.register_factory(SourceType.RasterDemSource, IRasterDemSource)
