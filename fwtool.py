""" Tool to pack and unpack Insta360 X3 firmware files. """

import json
from hashlib import md5
from io import BytesIO
from os import SEEK_END, SEEK_SET
from pathlib import Path
from struct import calcsize, pack, unpack
from typing import BinaryIO, TypeVar
from zlib import crc32

MD5_LEN = 16
TRAILER_FORMAT = "<I32s32s16s8sQ"
HEADER_FORMAT1 = "<32sII8s"
HEADER_SEG_FORMAT = "<II"
HEADER_SEG_COUNT = 16
HEADER_EXTRA_LEN = 0x180
SEGHEADER_FORMAT = "<IIIIIII228s"
ROMFS_HEADER_LEN = 0xA000
ROMFS_BLOCK_LEN = 2048

HEADER_MAGIC = 0x8732DFE6
SEGMENT_VERSION = 0x01000000
SEGMENT_MAGIC = 0xA324EB90
ROMFS_MAGIC = 0x66FC328A

T = TypeVar("T")


def validate_eq(actual: T, expected: T, desc: str):
    if actual != expected:
        raise ValueError(f"validation failed on {desc}: got {actual} but expected {expected}")


def validate_padding(data: bytes):
    if data != bytes(len(data)):
        raise ValueError(f"padding of length {len(data)} was not all zero!")


def _decode_trailer(file: BinaryIO) -> tuple[dict, bytes]:
    metadata = {}

    tail_size = calcsize(TRAILER_FORMAT) + MD5_LEN
    file.seek(0, SEEK_END)
    total_size = file.tell()

    ## read parts of the file
    file.seek(0, SEEK_SET)
    data = file.read(total_size - tail_size)
    trailer = file.read(calcsize(TRAILER_FORMAT))
    final_hash = file.read(MD5_LEN)
    validate_eq(file.read(), b"", "trailing data")

    ## compute hashes
    m = md5(data)
    h1 = m.digest()
    m.update(trailer)
    h2 = m.digest()
    validate_eq(h2, final_hash, "final hash")

    ## decode trailer
    body_size, product_name, version_name, body_hash, hw_id, hw_rev = unpack(TRAILER_FORMAT, trailer)
    product_name = product_name.rstrip(b"\0").decode("latin1")
    version_name = version_name.rstrip(b"\0").decode("latin1")
    hw_id = hw_id.decode("latin1")

    ## check to make sure this is a firmware file we understand
    validate_eq(product_name, "onex3", "product name")
    validate_eq(hw_id, "WFNI3XNO", "hardware ID")
    validate_eq(hw_rev, 1, "hardware revision")
    validate_eq(body_size, len(data), "size without trailer")
    validate_eq(h1, body_hash, "hash without trailer")

    metadata["product_name"] = product_name
    metadata["version_name"] = version_name
    metadata["hw_id"] = hw_id
    metadata["hw_rev"] = hw_rev

    return metadata, data


def _decode_body(file: BinaryIO) -> tuple[dict, list[bytes]]:
    metadata: dict = {}

    ## Decode first part of header
    zero1, magic, body_crc, zero2 = unpack(HEADER_FORMAT1, file.read(calcsize(HEADER_FORMAT1)))
    validate_padding(zero1)
    validate_eq(magic, HEADER_MAGIC, "header magic")
    validate_padding(zero2)

    ## Decode segment list, remove empty segments
    seg_infos = [unpack(HEADER_SEG_FORMAT, file.read(calcsize(HEADER_SEG_FORMAT))) for _ in range(HEADER_SEG_COUNT)]
    while seg_infos and seg_infos[-1] == (0, 0):
        seg_infos.pop()

    ## We do not interpret the final part of the header;
    ## it appears to contain offsets and other information pertaining to the first segment (the ARM program).
    extra = file.read(HEADER_EXTRA_LEN)
    metadata["header_extra"] = extra.hex()

    validate_eq(len(seg_infos), 6, "number of segments")

    ## Load and validate each segment
    metadata["segments"] = []
    segments = []
    running_crc = 0
    for seg_size, seg_crc in seg_infos:
        sf_header = file.read(calcsize(SEGHEADER_FORMAT))
        (
            sh_crc,
            sh_version,
            sh_date,
            sh_size,
            sh_extra1,
            sh_extra2,
            sh_magic,
            sh_padding,
        ) = unpack(SEGHEADER_FORMAT, sf_header)
        validate_eq(sh_version, SEGMENT_VERSION, "segment version?")
        validate_eq(sh_magic, SEGMENT_MAGIC, "segment magic")
        validate_padding(sh_padding)
        if seg_size != 0:
            validate_eq(seg_size, sh_size + calcsize(SEGHEADER_FORMAT), "segment size")

        sf_data = file.read(sh_size)
        running_crc = crc32(sf_header, running_crc)
        running_crc = crc32(sf_data, running_crc)
        sf_data_crc = crc32(sf_data)
        validate_eq(sf_data_crc, sh_crc, "segment data crc")
        validate_eq(0xFFFF_FFFF - running_crc, seg_crc, "segment running crc")

        seg_metadata = {
            "version": sh_version,
            "date": sh_date,
            "extra1": sh_extra1,
            "extra2": sh_extra2,
        }
        metadata["segments"].append(seg_metadata)
        segments.append(sf_data)

    validate_eq(file.read(), b"", "trailing data")
    validate_eq(running_crc, body_crc, "body crc")
    return metadata, segments


def decode_fw(file: BinaryIO, outdir: Path):
    # replace file with the trailer-less file
    trailer_metadata, body = _decode_trailer(file)
    header_metadata, segments = _decode_body(BytesIO(body))

    outdir.mkdir(parents=True, exist_ok=True)
    with open(outdir / "metadata.json", "w") as outf:
        json.dump({**trailer_metadata, **header_metadata}, outf)

    for i, seg in enumerate(segments):
        with open(outdir / f"f{i}.bin", "wb") as outf:
            outf.write(seg)


def _encode_body(metadata: dict, segment_data: list[bytes]) -> bytes:
    seg_infos = []

    body = bytearray()
    running_crc = 0
    validate_eq(len(metadata["segments"]), len(segment_data), "number of segments")

    for seg_md, sf_data in zip(metadata["segments"], segment_data):
        sf_header = pack(
            SEGHEADER_FORMAT,
            crc32(sf_data),
            seg_md["version"],
            seg_md["date"],
            len(sf_data),
            seg_md["extra1"],
            seg_md["extra2"],
            SEGMENT_MAGIC,
            b"",
        )
        running_crc = crc32(sf_header, running_crc)
        running_crc = crc32(sf_data, running_crc)
        body += sf_header
        body += sf_data
        seg_infos.append([len(sf_header) + len(sf_data), 0xFFFF_FFFF - running_crc])

    header = pack(HEADER_FORMAT1, b"", HEADER_MAGIC, running_crc, b"")
    # zero out the size of the last segment in the header
    seg_infos[-1][0] = 0
    while len(seg_infos) < HEADER_SEG_COUNT:
        seg_infos.append([0, 0])
    for i in range(HEADER_SEG_COUNT):
        header += pack(HEADER_SEG_FORMAT, *seg_infos[i])
    header += bytes.fromhex(metadata["header_extra"])

    return header + bytes(body)


def _encode_trailer(metadata: dict, body: bytes) -> bytes:
    m = md5(body)
    trailer = pack(
        TRAILER_FORMAT,
        len(body),
        metadata["product_name"].encode(),
        metadata["version_name"].encode(),
        m.digest(),
        metadata["hw_id"].encode(),
        metadata["hw_rev"],
    )
    m.update(trailer)
    return trailer + m.digest()


def encode_fw(fwdir: Path) -> bytes:
    with open(fwdir / "metadata.json", "r") as inf:
        metadata = json.load(inf)

    segment_data = []
    for i in range(len(metadata["segments"])):
        with open(fwdir / f"f{i}.bin", "rb") as inf:
            segment_data.append(inf.read())

    body = _encode_body(metadata, segment_data)
    trailer = _encode_trailer(metadata, body)

    return body + trailer


def decode_romfs(file: BinaryIO, outdir: Path):
    magic, subf_count = unpack("<II", file.read(8))
    validate_eq(magic, ROMFS_MAGIC, "romfs magic")

    subf_files = [unpack("<64sIII", file.read(76)) for _ in range(subf_count)]
    for subf_fn, subf_size, subf_offset, subf_hash in subf_files:
        subf_fn = subf_fn.rstrip(b"\0").decode()
        padding = file.read(subf_offset - file.tell())
        validate_padding(padding)
        validate_eq(subf_offset % ROMFS_BLOCK_LEN, 0, "file must be block-aligned")
        subf_data = file.read(subf_size)

        validate_eq(crc32(subf_data), subf_hash, "romfs file crc")
        with open(outdir / subf_fn, "wb") as outf:
            outf.write(subf_data)

    padding = file.read()
    validate_padding(padding)

    with open(outdir / "__filelist__.txt", "w") as outf:
        for subf_fn, *_ in subf_files:
            print(subf_fn.rstrip(b"\0").decode(), file=outf)


def encode_romfs(indir: Path) -> bytes:
    # We use the filelist in order to produce a romfs with the files in the same order as the original firmware
    filelist = indir / "__filelist__.txt"
    if filelist.is_file():
        filenames = [row.strip() for row in open(filelist)]
    else:
        print("Warning: __filelist__.txt not found; packing all files in the directory")
        filenames = list(indir.iterdir())

    header = bytearray(pack("<II", ROMFS_MAGIC, len(filenames)))
    data = bytearray()
    for filename in filenames:
        with open(indir / filename, "rb") as inf:
            subf_data = inf.read()

        header += pack("<64sIII", filename.encode(), len(subf_data), len(data) + ROMFS_HEADER_LEN, crc32(subf_data))
        data += subf_data
        # note that we add padding even when we are already at a multiple of the block size
        data += bytes(ROMFS_BLOCK_LEN - (len(data) % ROMFS_BLOCK_LEN))

    assert len(header) < ROMFS_HEADER_LEN, "Too many files in the romfs"
    return header + bytes(ROMFS_HEADER_LEN - len(header)) + data


def parse_args(argv):
    import argparse

    parser = argparse.ArgumentParser(description="Pack or unpack a firmware or romfs file")
    parser.add_argument("operation", help="Operation", choices=("pack", "unpack", "pack-romfs", "unpack-romfs"))
    parser.add_argument("fwfile", help="Packed firmware file", type=Path)
    parser.add_argument("fwdir", help="Unpacked directory", type=Path)

    args = parser.parse_args(argv)
    return args


def main(argv):
    args = parse_args(argv)

    if args.operation == "unpack":
        decode_fw(open(args.fwfile, "rb"), args.fwdir)
    elif args.operation == "pack":
        data = encode_fw(args.fwdir)
        with open(args.fwfile, "wb") as outf:
            outf.write(data)
    elif args.operation == "unpack-romfs":
        decode_romfs(open(args.fwfile, "rb"), args.fwdir)
    elif args.operation == "pack-romfs":
        data = encode_romfs(args.fwdir)
        with open(args.fwfile, "wb") as outf:
            outf.write(data)


if __name__ == "__main__":
    import sys

    exit(main(sys.argv[1:]))
