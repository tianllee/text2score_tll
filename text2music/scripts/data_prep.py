from music21 import converter, instrument, note, chord

def parse_midi(file_path):
    midi_data = converter.parse(file_path)
    melody_track = midi_data.parts[0]  # Get the first track (melody track)
    
    for element in melody_track.flat.notesAndRests:
        if isinstance(element, note.Note):
            print(f"Note: {element.name}, Onset: {element.offset}, Duration: {element.quarterLength}, MIDI Pitch: {element.pitch.midi}")
        elif isinstance(element, note.Rest):
            print(f"Rest: Onset: {element.offset}, Duration: {element.quarterLength}")

if __name__ == "__main__":
    file_path = '/import/c4dm-datasets-ext/POP909/001/001.mid'  # Replace with your MIDI file path
    parse_midi(file_path)