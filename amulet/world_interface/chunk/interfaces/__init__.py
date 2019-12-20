from __future__ import annotations

import os
import numpy
from typing import Tuple, Any, Union

from amulet.api.chunk import Chunk
from amulet.api.block_entity import BlockEntity
from amulet.api.entity import Entity
from amulet.world_interface.chunk import translators
from amulet.world_interface.loader import Loader
import amulet_nbt

SUPPORTED_INTERFACE_VERSION = 0
SUPPORTED_META_VERSION = 0

INTERFACES_DIRECTORY = os.path.dirname(__file__)

loader = Loader(
    "interface",
    INTERFACES_DIRECTORY,
    SUPPORTED_META_VERSION,
    SUPPORTED_INTERFACE_VERSION,
)


class Interface:
    def decode(self, cx: int, cz: int, data: Any) -> Tuple[Chunk, numpy.ndarray]:
        """
        Create an amulet.api.chunk.Chunk object from raw data given by the format
        :param cx: chunk x coordinate
        :type cx: int
        :param cz: chunk z coordinate
        :type cz: int
        :param data: Raw chunk data provided by the format.
        :type data: Any
        :return: Chunk object in version-specific format, along with the palette for that chunk.
        :rtype: Chunk
        """
        raise NotImplementedError()

    @staticmethod
    def _decode_entity(nbt: amulet_nbt.NBTFile, id_type: str, coord_type: str) -> Union[Tuple[str, str, Union[int, float], Union[int, float], Union[int, float], amulet_nbt.NBTFile], None]:
        if not isinstance(nbt, amulet_nbt.NBTFile) and isinstance(nbt.value, amulet_nbt.TAG_Compound):
            return

        if id_type in ['namespace-str-id', 'namespace-str-identifier', 'str-id']:
            id_key = 'identifier' if id_type == 'namespace-str-identifier' else 'id'

            entity_id = nbt.pop(id_key, amulet_nbt.TAG_String(''))

            if not isinstance(entity_id, amulet_nbt.TAG_String) or entity_id.value == '':
                return

            if id_type == 'str-id':
                namespace = None
                base_name = entity_id.value
            else:
                if ':' not in entity_id.value:
                    return
                namespace, base_name = entity_id.value.split(':', 1)
        else:
            return

        if coord_type in ['Pos-list-double', 'Pos-list-float']:
            if 'Pos' not in nbt:
                return
            pos = nbt.pop('Pos')
            pos: amulet_nbt.TAG_List
            if not (5 <= pos.list_data_type <= 6 and len(pos) == 3):
                return
            x, y, z = [c.value for c in pos]
        elif coord_type == 'xyz-int':
            if not all(c in nbt and isinstance(nbt[c], amulet_nbt.TAG_Int) for c in ('x', 'y', 'z')):
                return
            x, y, z = [nbt[c].value for c in ('x', 'y', 'z')]
        else:
            return

        return namespace, base_name, x, y, z, nbt

    def encode(
        self,
        chunk: Chunk,
        palette: numpy.ndarray,
        max_world_version: Tuple[str, Union[int, Tuple[int, int, int]]],
    ) -> Any:
        """
        Take a version-specific chunk and encode it to raw data for the format to store.
        :param chunk: The already translated version-specfic chunk to encode.
        :type chunk: Chunk
        :param palette: The palette the ids in the chunk correspond to.
        :type palette: numpy.ndarray[Block]
        :return: Raw data to be stored by the Format.
        :rtype: Any
        """
        raise NotImplementedError()

    @staticmethod
    def _encode_entity(entity: Union[Entity, BlockEntity], id_type: str, coord_type: str) -> Union[amulet_nbt.NBTFile, None]:
        if not isinstance(entity.nbt, amulet_nbt.NBTFile) and isinstance(entity.nbt.value, amulet_nbt.TAG_Compound):
            return
        nbt = entity.nbt

        if id_type == 'namespace-str-id':
            nbt['id'] = amulet_nbt.TAG_String(entity.namespaced_name)
        elif id_type == 'namespace-str-identifier':
            nbt['identifier'] = amulet_nbt.TAG_String(entity.namespaced_name)
        elif id_type == 'str-id':
            nbt['id'] = amulet_nbt.TAG_String(entity.base_name)
        else:
            return

        if coord_type == 'Pos-list-double':
            nbt['Pos'] = amulet_nbt.TAG_List([
                amulet_nbt.TAG_Double(float(entity.x)),
                amulet_nbt.TAG_Double(float(entity.y)),
                amulet_nbt.TAG_Double(float(entity.z))
            ])
        elif coord_type == 'Pos-list-float':
            nbt['Pos'] = amulet_nbt.TAG_List([
                amulet_nbt.TAG_Float(float(entity.x)),
                amulet_nbt.TAG_Float(float(entity.y)),
                amulet_nbt.TAG_Float(float(entity.z))
            ])
        elif coord_type == 'xyz-int':
            nbt['x'] = amulet_nbt.TAG_Int(int(entity.x))
            nbt['y'] = amulet_nbt.TAG_Int(int(entity.y))
            nbt['z'] = amulet_nbt.TAG_Int(int(entity.z))
        else:
            return

        return nbt

    def get_translator(
        self,
        max_world_version: Tuple[str, Union[int, Tuple[int, int, int]]],
        data: Any = None,
    ) -> Tuple[translators.Translator, Union[int, Tuple[int, int, int]]]:
        """
        Get the Translator class for the requested version.
        :param max_world_version: The game version the world was last opened in.
        :type max_world_version: Java: int (DataVersion)    Bedrock: Tuple[int, int, int, ...] (game version number)
        :param data: Optional data to get translator based on chunk version rather than world version
        :param data: Any
        :return: Tuple[Translator, version number for PyMCTranslate to use]
        :rtype: Tuple[translators.Translator, Union[int, Tuple[int, int, int]]]
        """
        raise NotImplementedError

    @staticmethod
    def is_valid(key: Tuple) -> bool:
        """
        Returns whether this Interface is able to interface with the chunk type with a given identifier key,
        generated by the format.

        :param key: The key who's decodability needs to be checked.
        :return: True if this interface can interface with the chunk version associated with the key, False otherwise.
        """
        raise NotImplementedError()


if __name__ == "__main__":
    import time

    print(loader.get_all())
    time.sleep(1)
    loader.reload()
    print(loader.get_all())
