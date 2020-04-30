from __future__ import annotations

import numpy
import copy
import math

from typing import Tuple, Callable, Union, List, Optional, TYPE_CHECKING, Any

from amulet import log, entity_support
from amulet.api.block import BlockManager, Block
from amulet.api.block_entity import BlockEntity
from amulet.api.entity import Entity
from amulet.api.chunk import Chunk
from amulet.api.data_types import (
    AnyNDArray,
    BlockNDArray,
    GetChunkCallback,
    TranslateBlockCallback,
    TranslateEntityCallback,
    BlockType,
    GetBlockCallback,
    TranslateBlockCallbackReturn,
    TranslateEntityCallbackReturn,
)

if TYPE_CHECKING:
    from PyMCTranslate import Version, TranslationManager


class Translator:
    def _translator_key(
        self, version_number: Union[int, Tuple[int, int, int]]
    ) -> Tuple[str, Union[int, Tuple[int, int, int]]]:
        """
        Return the version key for PyMCTranslate

        :return: The tuple version key for PyMCTranslate
        """
        raise NotImplementedError()

    @staticmethod
    def is_valid(key: Tuple) -> bool:
        """
        Returns whether this translator is able to translate the chunk type with a given identifier key,
        generated by the decoder.

        :param key: The key who's decodability needs to be checked.
        :return: True if this translator is able to translate the chunk type associated with the key, False otherwise.
        """
        raise NotImplementedError()

    @staticmethod
    def _translate(
        chunk: Chunk,
        palette: BlockNDArray,
        get_chunk_callback: Optional[
            GetChunkCallback
        ],
        translate_block: TranslateBlockCallback,
        translate_entity: TranslateEntityCallback,
        full_translate: bool,
    ) -> Tuple[Chunk, BlockNDArray]:
        if not full_translate:
            return chunk, palette

        todo = []
        output_block_entities = []
        output_entities = []
        finished = BlockManager()
        palette_mappings = {}

        # translate each block without using the callback
        for i, input_block in enumerate(palette):
            input_block: BlockType
            output_block, output_block_entity, output_entity, extra = translate_block(
                input_block, None
            )
            if extra and get_chunk_callback:
                todo.append(i)
            elif output_block is not None:
                palette_mappings[i] = finished.get_add_block(output_block)
                if output_block_entity is not None:
                    for cy in chunk.blocks.sub_chunks:
                        for x, y, z in zip(*numpy.where(chunk.blocks.get_sub_chunk(cy) == i)):
                            output_block_entities.append(output_block_entity.new_at_location(
                                x + chunk.cx * 16, y + cy * 16, z + chunk.cz * 16
                            ))
            else:
                # TODO: set the block to air
                pass

            if output_entity and entity_support:
                for cy in chunk.blocks.sub_chunks:
                    for x, y, z in zip(*numpy.where(chunk.blocks.get_sub_chunk(cy) == i)):
                        x += chunk.cx * 16
                        y += cy * 16
                        z += chunk.cz * 16
                        for entity in output_entity:
                            e = copy.deepcopy(entity)
                            e.location += (x, y, z)
                            output_entities.append(e)

        # re-translate the blocks that require extra information
        block_mappings = {}
        for index in todo:
            for cy in chunk.blocks.sub_chunks:
                for x, y, z in zip(*numpy.where(chunk.blocks.get_sub_chunk(cy) == index)):
                    y += cy * 16

                    def get_block_at(
                        pos: Tuple[int, int, int]
                    ) -> Tuple[Block, Optional[BlockEntity]]:
                        """Get a block at a location relative to the current block"""
                        nonlocal x, y, z, palette, chunk, cy

                        # calculate position relative to chunk base
                        dx, dy, dz = pos
                        dx += x
                        dy += y
                        dz += z

                        abs_x = dx + chunk.cx * 16
                        abs_y = dy
                        abs_z = dz + chunk.cz * 16

                        # calculate relative chunk position
                        cx = dx // 16
                        cz = dz // 16
                        if cx == 0 and cz == 0:
                            # if it is the current chunk
                            block = palette[chunk.blocks[dx, dy, dz]]
                            if isinstance(
                                block, tuple
                            ):  # bedrock palette is made of (version, Block). TODO: Perhaps find a better way to do this
                                block = block[0][1]
                            return block, chunk.block_entities.get((abs_x, abs_y, abs_z))

                        # if it is in a different chunk
                        local_chunk, local_palette = get_chunk_callback(cx, cz)
                        block = local_palette[local_chunk.blocks[dx % 16, dy, dz % 16]]
                        if isinstance(
                            block, tuple
                        ):  # bedrock palette is made of (version, Block). TODO: Perhaps find a better way to do this
                            block = block[0][1]
                        return (
                            block,
                            local_chunk.block_entities.get((abs_x, abs_y, abs_z)),
                        )

                    input_block = palette[chunk.blocks[x, y, z]]
                    output_block, output_block_entity, output_entity, _ = translate_block(
                        input_block, get_block_at
                    )
                    if output_block is not None:
                        block_mappings[(x, y, z)] = finished.get_add_block(output_block)
                        if output_block_entity is not None:
                            output_block_entities.append(output_block_entity.new_at_location(
                                x + chunk.cx * 16, y, z + chunk.cz * 16
                            ))
                    else:
                        # TODO: set the block to air
                        pass

                    if output_entity and entity_support:
                        for entity in output_entity:
                            e = copy.deepcopy(entity)
                            e.location += (x, y, z)
                            output_entities.append(e)

        if entity_support:
            for entity in chunk.entities:
                output_block, output_block_entity, output_entity = translate_entity(entity)
                if output_block is not None:
                    block_location = (int(math.floor(entity.x)), int(math.floor(entity.y)), int(math.floor(entity.z)))
                    block_mappings[block_location] = output_block
                    if output_block_entity:
                        output_block_entities.append(output_block_entity.new_at_location(*block_location))
                if output_entity:
                    for e in output_entity:
                        e.location = entity.location
                        output_entities.append(e)

        for cy in chunk.blocks.sub_chunks:
            old_blocks = chunk.blocks.get_sub_chunk(cy)
            new_blocks = numpy.zeros(old_blocks.shape, dtype=old_blocks.dtype)
            for old, new in palette_mappings.items():
                new_blocks[old_blocks == old] = new
            chunk.blocks.add_sub_chunk(cy, new_blocks)
        for (x, y, z), new in block_mappings.items():
            chunk.blocks[x, y, z] = new
        chunk.block_entities = output_block_entities
        chunk.entities = output_entities
        return chunk, numpy.array(finished.blocks())

    def to_universal(
        self,
        chunk_version: Union[int, Tuple[int, int, int]],
        translation_manager: 'TranslationManager',
        chunk: Chunk,
        palette: BlockNDArray,
        get_chunk_callback: Optional[GetChunkCallback],
        full_translate: bool,
    ) -> Tuple[Chunk, BlockNDArray]:
        """
        Translate an interface-specific chunk into the universal format.

        :param chunk_version: The version number (int or tuple) of the input chunk
        :param translation_manager: TranslationManager used for the translation
        :param chunk: The chunk to translate.
        :param palette: The palette that the chunk's indices correspond to.
        :param get_chunk_callback: function callback to get a chunk's data
        :param full_translate: if true do a full translate. If false just unpack the palette (used in callback)
        :return: Chunk object in the universal format.
        """
        version = translation_manager.get_version(*self._translator_key(chunk_version))

        def translate_block(
            input_object: Block,
            get_block_callback: Optional[GetBlockCallback],
        ) -> TranslateBlockCallbackReturn:
            final_block = None
            final_block_entity = None
            final_entities = []
            final_extra = False

            for depth, block in enumerate(
                (input_object.base_block,) + input_object.extra_blocks
            ):
                (
                    output_object,
                    output_block_entity,
                    extra,
                ) = version.block.to_universal(block, get_block_callback)

                if isinstance(output_object, Block):
                    if not output_object.namespace.startswith("universal"):
                        log.debug(
                            f"Error translating {input_object.blockstate} to universal. Got {output_object.blockstate}"
                        )
                    if final_block is None:
                        final_block = output_object
                    else:
                        final_block += output_object
                    if depth == 0:
                        final_block_entity = output_block_entity

                elif isinstance(output_object, Entity):
                    final_entities.append(output_object)
                    # TODO: offset entity coords

                final_extra |= extra

            return final_block, final_block_entity, final_entities, final_extra

        def translate_entity(
            input_object: Entity
        ) -> TranslateEntityCallbackReturn:
            final_block = None
            final_block_entity = None
            final_entities = []
            # TODO
            return final_block, final_block_entity, final_entities

        chunk.biomes = self._biomes_to_universal(version, chunk.biomes)
        if version.block_entity_map is not None:
            for block_entity in chunk.block_entities:
                block_entity: BlockEntity
                if (
                    block_entity.namespace is None
                    and block_entity.base_name in version.block_entity_map
                ):
                    block_entity.namespaced_name = version.block_entity_map[
                        block_entity.base_name
                    ]
                else:
                    log.debug(
                        f"Could not find pretty name for block entity {block_entity.namespaced_name}"
                    )
        return self._translate(
            chunk, palette, get_chunk_callback, translate_block, translate_entity, full_translate
        )

    def from_universal(
        self,
        max_world_version_number: Union[int, Tuple[int, int, int]],
        translation_manager: 'TranslationManager',
        chunk: Chunk,
        palette: BlockNDArray,
        get_chunk_callback: Optional[GetChunkCallback],
        full_translate: bool,
    ) -> Tuple[Chunk, BlockNDArray]:
        """
        Translate a universal chunk into the interface-specific format.

        :param max_world_version_number: The version number (int or tuple) of the max world version
        :param translation_manager: TranslationManager used for the translation
        :param chunk: The chunk to translate.
        :param palette: The palette that the chunk's indices correspond to.
        :param get_chunk_callback: function callback to get a chunk's data
        :param full_translate: if true do a full translate. If false just pack the palette (used in callback)
        :return: Chunk object in the interface-specific format and palette.
        """
        version = translation_manager.get_version(
            *self._translator_key(max_world_version_number)
        )

        # TODO: perhaps find a way so this code isn't duplicated in three places
        def translate_block(
            input_object: Block,
            get_block_callback: Optional[GetBlockCallback],
        ) -> TranslateBlockCallbackReturn:
            final_block = None
            final_block_entity = None
            final_entities = []
            final_extra = False

            for depth, block in enumerate(
                (input_object.base_block,) + input_object.extra_blocks
            ):
                (
                    output_object,
                    output_block_entity,
                    extra,
                ) = version.block.from_universal(block, get_block_callback)

                if isinstance(output_object, Block):
                    if __debug__ and output_object.namespace.startswith(
                        "universal"
                    ):
                        log.debug(
                            f"Error translating {input_object.blockstate} from universal. Got {output_object.blockstate}"
                        )
                    if final_block is None:
                        final_block = output_object
                    else:
                        final_block += output_object
                    if depth == 0:
                        final_block_entity = output_block_entity

                elif isinstance(output_object, Entity):
                    final_entities.append(output_object)
                    # TODO: offset entity coords

                final_extra |= extra

            return final_block, final_block_entity, final_entities, final_extra

        def translate_entity(
            input_object: Entity
        ) -> TranslateEntityCallbackReturn:
            final_block = None
            final_block_entity = None
            final_entities = []
            # TODO
            return final_block, final_block_entity, final_entities

        chunk, palette = self._translate(
            chunk, palette, get_chunk_callback, translate_block, translate_entity, full_translate
        )
        palette = self._pack_palette(version, palette)
        chunk.biomes = self._biomes_from_universal(version, chunk.biomes)
        if version.block_entity_map is not None:
            for block_entity in chunk.block_entities:
                block_entity: BlockEntity
                if block_entity.namespaced_name in version.block_entity_map_inverse:
                    block_entity.namespaced_name = version.block_entity_map_inverse[
                        block_entity.namespaced_name
                    ]
                else:
                    log.debug(
                        f"Could not find pretty name for block entity {block_entity.namespaced_name}"
                    )
        return chunk, palette

    @staticmethod
    def _biomes_to_universal(translator_version: 'Version', biome_array):
        biome_palette, biome_compact_array = numpy.unique(
            biome_array, return_inverse=True
        )
        universal_biome_palette = numpy.array(
            [translator_version.biome.to_universal(biome) for biome in biome_palette]
        )
        return universal_biome_palette[biome_compact_array]

    @staticmethod
    def _biomes_from_universal(translator_version: 'Version', biome_array):
        biome_palette, biome_compact_array = numpy.unique(
            biome_array, return_inverse=True
        )
        universal_biome_palette = numpy.array(
            [translator_version.biome.from_universal(biome) for biome in biome_palette]
        )
        return universal_biome_palette[biome_compact_array]

    def unpack(
            self,
            chunk_version: Union[int, Tuple[int, int, int]],
            translation_manager: 'TranslationManager',
            chunk: Chunk,
            palette: AnyNDArray
    ) -> Tuple[Chunk, AnyNDArray]:
        """
        Unpack the version-specific palette into the stringified version where needed.

        :return: The palette converted to block objects.
        """
        version = translation_manager.get_version(*self._translator_key(chunk_version))
        palette = self._unpack_palette(version, palette)
        return chunk, palette

    def _unpack_palette(
        self, version: 'Version', palette: AnyNDArray
    ) -> BlockNDArray:
        """
        Unpack the version-specific palette into the stringified version where needed.

        :return: The palette converted to block objects.
        """
        return palette

    def pack(
            self,
            max_world_version_number: Union[int, Tuple[int, int, int]],
            translation_manager: 'TranslationManager',
            chunk: Chunk,
            palette: BlockNDArray
    ) -> Tuple[Chunk, AnyNDArray]:
        """
        Translate the list of block objects into a version-specific palette.
        :return: The palette converted into version-specific blocks (ie id, data tuples for 1.12)
        """
        version = translation_manager.get_version(
            *self._translator_key(max_world_version_number)
        )
        palette = self._pack_palette(version, palette)
        return chunk, palette

    def _pack_palette(self, version: 'Version', palette: BlockNDArray) -> AnyNDArray:
        """
        Translate the list of block objects into a version-specific palette.
        :return: The palette converted into version-specific blocks (ie id, data tuples for 1.12)
        """
        return palette
