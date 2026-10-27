void
wrap(ImagePointer image)
{
  GetPipelineObjectRegistry()->LookupImageByName(outputImageNameForEachStage, defaultStageIndices)->Allocate(true);
  image->Allocate(true);
}
