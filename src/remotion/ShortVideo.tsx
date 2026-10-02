import {AbsoluteFill, Sequence} from 'remotion';
import {AudioLayer} from './AudioLayer.js';
import {BackgroundVisual} from './BackgroundVisual.js';
import {CaptionsOverlay} from './CaptionsOverlay.js';
import {ProgressBar} from './ProgressBar.js';
import type {VideoProject} from './types.js';

export const ShortVideo = (project: VideoProject): React.ReactNode => (
  <AbsoluteFill style={{backgroundColor: '#05070d'}}>
    {project.scenes.map((scene) => (
      <Sequence
        key={scene.sceneId}
        from={scene.startFrame}
        durationInFrames={scene.durationInFrames}
      >
        <BackgroundVisual scene={scene} />
      </Sequence>
    ))}
    <CaptionsOverlay captions={project.captions} />
    <ProgressBar />
    <AudioLayer project={project} />
  </AbsoluteFill>
);
