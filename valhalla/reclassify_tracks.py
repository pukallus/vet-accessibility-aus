#!/usr/bin/env python3
"""
Reclassify highway=track to highway=unclassified in OSM PBF
This makes tracks routable by Valhalla's auto costing model.

Requirements: pip install osmium
"""

import osmium
import sys

class TrackReclassifier(osmium.SimpleHandler):
    """Reclassify highway=track to highway=unclassified"""

    def __init__(self, writer):
        super().__init__()
        self.writer = writer
        self.track_count = 0

    def node(self, n):
        """Pass through all nodes unchanged"""
        self.writer.add_node(n)

    def way(self, w):
        """Process each way"""
        # Check if this is a track
        if 'highway' in w.tags and w.tags['highway'] == 'track':
            self.track_count += 1

            # Create list of tag tuples for mutable Way
            new_tags = []
            for k, v in w.tags:
                if k == 'highway':
                    new_tags.append(('highway', 'unclassified'))
                else:
                    new_tags.append((k, v))

            # Add surface tag if not present
            if 'surface' not in w.tags:
                new_tags.append(('surface', 'unpaved'))

            # Create modified way
            mutable_way = osmium.osm.mutable.Way(w)
            mutable_way.tags = new_tags
            self.writer.add_way(mutable_way)
        else:
            # Keep way unchanged
            self.writer.add_way(w)

    def relation(self, r):
        """Pass through all relations unchanged"""
        self.writer.add_relation(r)

def reclassify_tracks(input_file, output_file):
    """Reclassify tracks in OSM PBF file"""

    print(f"Reading: {input_file}")
    print(f"Writing: {output_file}")
    print("Reclassifying highway=track → highway=unclassified...")

    writer = osmium.SimpleWriter(output_file)
    handler = TrackReclassifier(writer)

    handler.apply_file(input_file)

    writer.close()

    print(f"Done! Reclassified {handler.track_count} tracks")
    print(f"\nNext steps:")
    print(f"1. Rebuild Valhalla tiles with: {output_file}")
    print(f"2. Restart Valhalla container")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python reclassify_tracks.py input.osm.pbf output.osm.pbf")
        sys.exit(1)

    reclassify_tracks(sys.argv[1], sys.argv[2])
