import {Audio, Sequence, staticFile} from 'remotion';
import type {VideoProject} from './types.js';

type AudioLayerProps = {
  project: VideoProject;
};

export const AudioLayer = ({project}: AudioLayerProps): React.ReactNode => (
  <>
    {project.backgroundMusicPath ? (
      <Audio
        src={staticFile(project.backgroundMusicPath)}
        volume={project.narrationPath ? 0.15 : 0.35}
        loop
      />
    ) : null}
    {project.narrationPath ? (
      <Audio src={staticFile(project.narrationPath)} volume={1} />
    ) : null}
    {project.scenes.map((scene) => {
      const path = scene.sfxTrigger
        ? project.sfxPaths[scene.sfxTrigger]
        : undefined;
      return path ? (
        <Sequence
          key={`${scene.sceneId}-${path}`}
          from={scene.startFrame}
          layout="none"
        >
          <Audio src={staticFile(path)} volume={0.55} />
        </Sequence>
      ) : null;
    })}
  </>
);
