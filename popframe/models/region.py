from functools import singledispatchmethod
from pydantic import BaseModel, InstanceOf
import dill as pickle
import shapely
import geopandas as gpd
import pandas as pd
from .geodataframe import GeoDataFrame, BaseRow

class RayonRow(BaseRow):
    name : str
    geometry : shapely.Polygon | shapely.MultiPolygon

class OkrugRow(BaseRow):
    name : str
    geometry : shapely.Polygon | shapely.MultiPolygon

class TownRow(BaseRow):
    name : str
    level: str
    geometry : shapely.Point
    population : int

class TerRow(BaseRow):
    name : str
    geometry : shapely.Polygon | shapely.MultiPolygon

class Town(BaseModel):
    id : int
    name : str
    population : int
    level: str
    geometry : InstanceOf[shapely.Point]

    def to_dict(self):
        res = {
            'id': self.id,
            'name': self.name,
            'population': self.population,
            'level' : self.level,
            'geometry': self.geometry
        }
        return res

    @classmethod
    def from_gdf(cls, gdf):
        res = {}
        for i in gdf.index:
            res[i] = cls(id=i, **gdf.loc[i].to_dict())
        return res 
    
class Region():

    def __init__(self, rayons : GeoDataFrame[RayonRow] | gpd.GeoDataFrame, okrugs : GeoDataFrame[OkrugRow] | gpd.GeoDataFrame, towns : GeoDataFrame[TownRow] | gpd.GeoDataFrame, adjacency_matrix : pd.DataFrame, territory : GeoDataFrame[TerRow] | gpd.GeoDataFrame,):
        if not isinstance(rayons, GeoDataFrame[RayonRow]):
            rayons = GeoDataFrame[RayonRow](rayons)
        if not isinstance(okrugs, GeoDataFrame[OkrugRow]):
            okrugs = GeoDataFrame[OkrugRow](okrugs)
        if not isinstance(towns, GeoDataFrame[TownRow]):
            towns = GeoDataFrame[TownRow](towns)
        if not isinstance(territory, GeoDataFrame[TerRow]):
            territory = GeoDataFrame[RayonRow](territory)
        assert (adjacency_matrix.index == adjacency_matrix.columns).all(), "Adjacency matrix indices and columns don't match"
        assert (adjacency_matrix.index == towns.index).all(), "Adjacency matrix indices and towns indices don't match"
        assert(rayons.crs == okrugs.crs and okrugs.crs == towns.crs and territory.crs == okrugs.crs), 'CRS should march everywhere'
        self.crs = towns.crs
        self.rayons = rayons
        self.territory = territory
        self.okrugs = okrugs
        self.adjacency_matrix = adjacency_matrix
        self._towns = Town.from_gdf(towns)

    def get_towns_gdf(self):
        towns = [town.to_dict() for town in self.towns]
        return gpd.GeoDataFrame(towns).set_index('id').set_crs(self.crs).fillna(0)

    def to_gdf(self):
        gdf = self.get_towns_gdf().sjoin(
            self.okrugs[['geometry', 'name']].rename(columns={'name': 'okrug_name'}),
            how='left',
            predicate='within',
            lsuffix='_town',
            rsuffix='_okrug'
        )
        gdf = gdf.sjoin(
            self.rayons[['geometry', 'name']].rename(columns={'name':'rayon_name'}),
            how='left',
            predicate='within',
            lsuffix='_town',
            rsuffix='_rayon'
        )
        return gdf.drop(columns=['index__okrug', 'index__rayon'])

    @singledispatchmethod
    def __getitem__(self, arg):
        raise NotImplementedError(f"Can't access object with such argument type {type(arg)}")

    # Make city_model subscriptable, to access block via ID like city_model[123]
    @__getitem__.register(int)
    def _(self, town_id):
        if not town_id in self._towns:
            raise KeyError(f"Can't find town with such id: {town_id}")
        return self._towns[town_id]

    # Make city_model subscriptable, to access service type via name like city_model['schools']

    @__getitem__.register(tuple)
    def _(self, towns):
        (town_a, town_b) = towns
        if isinstance(town_a, Town):
            town_a = town_a.id
        if isinstance(town_b, Town):
            town_b = town_b.id
        return self.adjacency_matrix.loc[town_a, town_b]

    @property
    def towns(self):
        return self._towns.values()