import {Composition} from 'remotion';
import {ShortVideo} from './ShortVideo.js';
import {
  DEFAULT_PROJECT,
  projectDurationInFrames,
  type VideoProject,
} from './types.js';

export const RemotionRoot = (): React.ReactNode => (
  <Composition
    id="ShortVideo"
    component={ShortVideo}
    width={1080}
    height={1920}
    fps={30}
    durationInFrames={90}
    defaultProps={DEFAULT_PROJECT}
    calculateMetadata={({props}: {props: VideoProject}) => ({
      durationInFrames: projectDurationInFrames(props),
      fps: props.fps,
    })}
  />
);
