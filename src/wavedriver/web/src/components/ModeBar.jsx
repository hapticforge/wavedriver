import { Waves, Scissors, Layers, Video, Music } from 'lucide-react';

const MODES = [
  { id: 'pattern',  label: 'Pattern',  Icon: Waves    },
  { id: 'edging',   label: 'Edging',   Icon: Scissors },
  { id: 'sequence', label: 'Sequence', Icon: Layers   },
  { id: 'video',    label: 'Video',    Icon: Video    },
  { id: 'audio',    label: 'Audio',    Icon: Music    },
];

export function ModeBar({ activeMode, setActiveMode }) {
  return (
    <nav className="mode-bar">
      {MODES.map(({ id, label, Icon }) => (
        <button
          key={id}
          className={`mode-tab${activeMode === id ? ' active' : ''}`}
          onClick={() => setActiveMode(id)}
        >
          <Icon size={13} />
          {label}
        </button>
      ))}
    </nav>
  );
}
