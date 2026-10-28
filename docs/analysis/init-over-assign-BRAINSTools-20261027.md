# init-over-assign: BRAINSTools 20261027_1926

Repo: BRAINSTools (60b069efa672) | Standalone: /Users/johnsonhj/src/BRAINSTools, build /Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-EPRelease-build

- Branch: `style-init-over-assign-20261027`
- Tip: `d781bcf0b16c41f464fb4093a2d72e7db8b90363`
- Run directory: /Users/johnsonhj/src/itk_forest_build_testbed/.devlocal/init-over-assign/BRAINSTools-20261027_1926

## Commits

| SHA | Kind | Files | Sites | Gate |
|---|---|---|---|---|
| `bd86769fc244` | member-init | 18 | 29 | 16 gate-failed |
| `55499601c1ba` | member-default-init | 1 | 1 | pass |
| `3b35d6cfeb82` | local-init | 14 | 44 | 67 gate-failed |
| `26314eb7f93b` | local-const | 9 | 21 | pass |
| `870a5c05ca42` | container-const | 2 | 5 | pass |
| `3db8b0af4af7` | itk-helpers | 5 | 13 | pass |
| `436de67eb159` | itk-helpers-constexpr | 2 | 6 | pass |
| `d781bcf0b16c` | narrow-scope | 49 | 81 | 37 gate-failed |

### `bd86769fc244` member-init

- backup-tree: 25cefaba4afd91dce82728465dd1d758191842a3
- gate failure in BRAINSABC/brainseg/BRAINSABCUtilities.cxx not attributed to a staged file
- gate failure in BRAINSABC/brainseg/BRAINSABC.cxx not attributed to a staged file
- gate failure in BRAINSABC/brainseg/GeneratePurePlugMask.cxx not attributed to a staged file
- gate failure in GTRACT/Cmdline/gtractCostFastMarching.cxx not attributed to a staged file

### `55499601c1ba` member-default-init

- backup-tree: ee15ba9d7a37503b33883a5798dd7ea18f70b6bd

### `3b35d6cfeb82` local-init

- DWIConvert/DWIConvertUtils.cxx:106: hunk moved to local-const with the rest of its site
- GTRACT/Common/itkGtractInverseDisplacementFieldImageFilter.hxx:129: hunk moved to local-const with the rest of its site
- backup-tree: ee15ba9d7a37503b33883a5798dd7ea18f70b6bd
- gate failure in BRAINSABC/brainseg/EMSegmentationFilter_float+float.cxx not attributed to a staged file
- gate failure in BRAINSABC/brainseg/BRAINSABC.cxx not attributed to a staged file
- gate failure in BRAINSConstellationDetector/src/BRAINSConstellationDetectorPrimary.cxx not attributed to a staged file
- gate failure in BRAINSConstellationDetector/src/BRAINSEyeDetector.cxx not attributed to a staged file
- gate failure in BRAINSConstellationDetector/src/landmarksConstellationDetectorCompute.cxx not attributed to a staged file
- gate failure in BRAINSConstellationDetector/src/landmarksConstellationWeights.cxx not attributed to a staged file
- gate failure in BRAINSConstellationDetector/src/BRAINSAlignMSP.cxx not attributed to a staged file
- gate failure in BRAINSConstellationDetector/src/BRAINSClipInferior.cxx not attributed to a staged file
- gate failure in BRAINSConstellationDetector/src/BRAINSTrimForegroundInDirection.cxx not attributed to a staged file
- gate failure in BRAINSConstellationDetector/src/PrepareOutputImages.cxx not attributed to a staged file
- gate failure in GTRACT/Cmdline/gtractFastMarchingTracking.cxx not attributed to a staged file
- gate failure in GTRACT/Cmdline/gtractFiberTracking.cxx not attributed to a staged file

### `26314eb7f93b` local-const

- backup-tree: f724b2afdb36ecaedda93dd1b8ed0534e5470c8d

### `870a5c05ca42` container-const

- backup-tree: f724b2afdb36ecaedda93dd1b8ed0534e5470c8d

### `3db8b0af4af7` itk-helpers

- backup-tree: f724b2afdb36ecaedda93dd1b8ed0534e5470c8d

### `436de67eb159` itk-helpers-constexpr

- backup-tree: f724b2afdb36ecaedda93dd1b8ed0534e5470c8d

### `d781bcf0b16c` narrow-scope

- backup-tree: f724b2afdb36ecaedda93dd1b8ed0534e5470c8d
- gate failure in BRAINSABC/brainseg/BRAINSABC.cxx not attributed to a staged file
- gate failure in BRAINSABC/brainseg/GeneratePurePlugMask.cxx not attributed to a staged file

## Disjoint commits

Disjoint from every other commit (candidates for separate PRs):
- `55499601c1ba` member-default-init
- `436de67eb159` itk-helpers-constexpr

## Skip list

### comment-stranded (12)

- BRAINSABC/brainseg/EMSegmentationFilter.hxx:628 member-init/prefer-member-initializer (comment above the assignment)
- BRAINSABC/brainseg/EMSegmentationFilter.hxx:631 member-init/prefer-member-initializer (comment above the assignment)
- BRAINSABC/brainseg/EMSegmentationFilter.hxx:634 member-init/prefer-member-initializer (comment above the assignment)
- BRAINSCommonLib/brainsiaTestingComparisonImageFilter.hxx:38 member-init/prefer-member-initializer (comment above the assignment)
- BRAINSCommonLib/brainsiaTestingComparisonImageFilter.hxx:41 member-init/prefer-member-initializer (comment above the assignment)
- BRAINSCommonLib/brainsiaTestingComparisonImageFilter.hxx:44 member-init/prefer-member-initializer (comment above the assignment)
- BRAINSConstellationDetector/src/BRAINSConstellationDetector2.hxx:47 member-init/prefer-member-initializer (comment above the assignment)
- BRAINSConstellationDetector/src/BRAINSConstellationDetector2.hxx:72 member-init/prefer-member-initializer (comment above the assignment)
- BRAINSConstellationDetector/src/BRAINSConstellationDetector2.hxx:91 member-init/prefer-member-initializer (comment above the assignment)
- BRAINSConstellationDetector/src/BRAINSConstellationDetector2.hxx:98 member-init/prefer-member-initializer (comment above the assignment)
- BRAINSConstellationDetector/src/BRAINSHoughEyeDetector.hxx:172 member-init/prefer-member-initializer (comment above the assignment)
- BRAINSConstellationDetector/src/BRAINSHoughEyeDetector.hxx:191 member-init/prefer-member-initializer (comment above the assignment)

### costly-construct (297)

- BRAINSABC/TestSuite/BlendImageFilterGTest.cxx:66 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSABC/TestSuite/BlendImageFilterGTest.cxx:67 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSABC/TestSuite/BlendImageFilterGTest.cxx:68 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSABC/brainseg/AtlasRegistrationMethod.hxx:146 narrow-scope/narrow-scope (call)
- BRAINSABC/brainseg/AtlasRegistrationMethod.hxx:147 narrow-scope/narrow-scope (call)
- BRAINSABC/brainseg/AtlasRegistrationMethod.hxx:212 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSABC/brainseg/AtlasRegistrationMethod.hxx:497 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSABC/brainseg/BRAINSABCUtilities.cxx:48 narrow-scope/narrow-scope (call)
- BRAINSABC/brainseg/BRAINSABCUtilities.cxx:109 narrow-scope/narrow-scope (call)
- BRAINSABC/brainseg/BRAINSABCUtilities.hxx:45 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSABC/brainseg/BRAINSABCUtilities.hxx:60 narrow-scope/narrow-scope (side-effect)
- BRAINSABC/brainseg/BRAINSABCUtilities.hxx:62 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSABC/brainseg/BRAINSABCUtilities.hxx:87 narrow-scope/narrow-scope (call)
- BRAINSABC/brainseg/BRAINSABCUtilities.hxx:144 narrow-scope/narrow-scope (side-effect)
- BRAINSABC/brainseg/BRAINSABCUtilities.hxx:150 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSABC/brainseg/ComputeDistributions.h:99 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSABC/brainseg/ComputeDistributions.h:125 narrow-scope/narrow-scope (call)
- BRAINSABC/brainseg/ComputeDistributions.h:126 narrow-scope/narrow-scope (call)
- BRAINSABC/brainseg/ComputeDistributions.h:154 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSABC/brainseg/ComputeDistributions.h:202 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSABC/brainseg/ComputeDistributions.h:227 narrow-scope/narrow-scope (call)
- BRAINSABC/brainseg/ComputeDistributions.h:228 narrow-scope/narrow-scope (call)
- BRAINSABC/brainseg/ComputeDistributions.h:285 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSABC/brainseg/ComputeDistributions.h:352 narrow-scope/narrow-scope (call)
- BRAINSABC/brainseg/LLSBiasCorrector.hxx:126 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSABC/brainseg/LLSBiasCorrector.hxx:138 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSABC/brainseg/LLSBiasCorrector.hxx:257 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSABC/brainseg/LLSBiasCorrector.hxx:366 narrow-scope/narrow-scope (non-trivial)
- BRAINSABC/brainseg/LLSBiasCorrector.hxx:475 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSABC/brainseg/LLSBiasCorrector.hxx:481 narrow-scope/narrow-scope (call)
- BRAINSABC/brainseg/LLSBiasCorrector.hxx:599 narrow-scope/narrow-scope (non-trivial)
- BRAINSABC/brainseg/LLSBiasCorrector.hxx:614 narrow-scope/narrow-scope (non-trivial)
- BRAINSABC/brainseg/LLSBiasCorrector.hxx:727 narrow-scope/narrow-scope (side-effect)
- BRAINSABC/brainseg/LLSBiasCorrector.hxx:795 narrow-scope/narrow-scope (side-effect)
- BRAINSABC/brainseg/OutputVolumeTemplate.h:33 narrow-scope/narrow-scope (call)
- BRAINSCommonLib/BRAINSComputeLabels.h:56 narrow-scope/narrow-scope (call)
- BRAINSCommonLib/BRAINSComputeLabels.h:82 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/BRAINSFitHelper.cxx:555 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/BRAINSFitHelper.cxx:556 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/BRAINSFitHelperTemplate.hxx:327 narrow-scope/narrow-scope (side-effect)
- BRAINSCommonLib/BRAINSFitHelperTemplate.hxx:706 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/BRAINSFitHelperTemplate.hxx:804 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/BRAINSFitHelperTemplate.hxx:882 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/BRAINSFitHelperTemplate.hxx:968 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/BRAINSFitHelperTemplate.hxx:1059 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/BRAINSFitHelperTemplate.hxx:1407 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/BRAINSFitHelperTemplate.hxx:1604 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/BRAINSFitHelperTemplate.hxx:1606 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/BRAINSFitSyN.h:160 narrow-scope/narrow-scope (side-effect)
- BRAINSCommonLib/BRAINSFitSyN.h:162 narrow-scope/narrow-scope (side-effect)
- BRAINSCommonLib/BRAINSFitSyN.h:170 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/BRAINSFitSyN.h:176 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/BRAINSFitUtils.h:190 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/BRAINSThreadControl.cxx:49 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/ConvertToRigidAffine.h:124 narrow-scope/narrow-scope (call)
- BRAINSCommonLib/DWIMetaDataDictionaryValidator.cxx:110 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/DWIMetaDataDictionaryValidator.cxx:240 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/DWIMetaDataDictionaryValidator.cxx:259 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/DWIMetaDataDictionaryValidator.cxx:282 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/DWIMetaDataDictionaryValidator.cxx:304 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/DWIMetaDataDictionaryValidator.cxx:340 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/GenericTransformImage.cxx:70 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/GenericTransformImage.cxx:141 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/GenericTransformImage.cxx:146 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/GenericTransformImage.cxx:163 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/GenericTransformImage.cxx:177 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/GenericTransformImage.cxx:199 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/GenericTransformImage.cxx:318 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/LinearRegressionIntensityMatching.h:136 narrow-scope/narrow-scope (non-trivial)
- BRAINSCommonLib/Slicer3LandmarkIO.cxx:233 narrow-scope/narrow-scope (call)
- BRAINSCommonLib/Slicer3LandmarkIO.cxx:234 narrow-scope/narrow-scope (call)
- BRAINSCommonLib/Slicer3LandmarkIO.cxx:235 narrow-scope/narrow-scope (call)
- BRAINSCommonLib/Slicer3LandmarkIO.cxx:245 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/Slicer3LandmarkIO.cxx:256 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/Slicer3LandmarkIO.cxx:326 narrow-scope/narrow-scope (call)
- BRAINSCommonLib/Slicer3LandmarkIO.cxx:327 narrow-scope/narrow-scope (call)
- BRAINSCommonLib/Slicer3LandmarkIO.cxx:328 narrow-scope/narrow-scope (call)
- BRAINSCommonLib/Slicer3LandmarkIO.cxx:338 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/Slicer3LandmarkIO.cxx:349 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/StandardizeMaskIntensity.h:195 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/StandardizeMaskIntensity.h:196 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/TestSuite/DWIMetaDataDictionaryValidatorGTest.cxx:94 narrow-scope/narrow-scope (call)
- BRAINSCommonLib/TestSuite/DWIMetaDataDictionaryValidatorGTest.cxx:114 narrow-scope/narrow-scope (call)
- BRAINSCommonLib/TestSuite/DWIMetaDataDictionaryValidatorGTest.cxx:289 narrow-scope/narrow-scope (call)
- BRAINSCommonLib/TestSuite/DWIMetaDataDictionaryValidatorGTest.cxx:323 narrow-scope/narrow-scope (call)
- BRAINSCommonLib/TestSuite/DWIMetaDataDictionaryValidatorTest.cxx:179 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/TestSuite/DWIMetaDataDictionaryValidatorTest.cxx:248 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/TestSuite/DWIMetaDataDictionaryValidatorTest.cxx:267 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/TestSuite/DWIMetaDataDictionaryValidatorTest.cxx:327 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/TestSuite/FindCenterOfBrain.cxx:60 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/TestSuite/ImgmathGTest.cxx:311 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/TestSuite/itkResampleInPlaceImageFilterTest.cxx:105 narrow-scope/narrow-scope (call)
- BRAINSCommonLib/TestSuite/itkResampleInPlaceImageFilterTest.cxx:107 narrow-scope/narrow-scope (call)
- BRAINSCommonLib/TestSuite/itkResampleInPlaceImageFilterTest.cxx:124 narrow-scope/narrow-scope (call)
- BRAINSCommonLib/TestSuite/itkResampleInPlaceImageFilterTest.cxx:126 narrow-scope/narrow-scope (call)
- BRAINSCommonLib/brainsiaTestingComparisonImageFilter.hxx:124 narrow-scope/narrow-scope (call)
- BRAINSCommonLib/brainsiaTestingComparisonImageFilter.hxx:152 narrow-scope/narrow-scope (call)
- BRAINSCommonLib/brainsiaTestingComparisonImageFilter.hxx:157 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/brainsiaTestingComparisonImageFilter.hxx:158 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/genericRegistrationHelper.h:285 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/genericRegistrationHelper.h:294 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/genericRegistrationHelper.hxx:371 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/itkBRAINSROIAutoImageFilter.h:143 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/itkBRAINSToolsTestMain.h:190 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/itkBRAINSToolsTestMain.h:307 narrow-scope/narrow-scope (side-effect)
- BRAINSCommonLib/itkBRAINSToolsTestMain.h:500 narrow-scope/narrow-scope (side-effect)
- BRAINSCommonLib/itkComputeHistogramQuantileThresholds.hxx:115 narrow-scope/narrow-scope (side-effect)
- BRAINSCommonLib/itkFindCenterOfBrainFilter.hxx:194 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/itkFindCenterOfBrainFilter.hxx:310 narrow-scope/narrow-scope (call)
- BRAINSCommonLib/itkFindCenterOfBrainFilter.hxx:326 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/itkIO.h:57 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/itkIO.h:58 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/itkIO.h:148 narrow-scope/narrow-scope (call)
- BRAINSCommonLib/itkIO.h:330 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/itkIO.h:331 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/itkIO.h:332 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/itkIO.h:333 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/itkMultiModeHistogramThresholdBinaryImageFilter.hxx:91 narrow-scope/narrow-scope (side-effect)
- BRAINSCommonLib/itkOtsuHistogramMatchingImageFilter.hxx:187 narrow-scope/narrow-scope (call)
- BRAINSCommonLib/itkOtsuHistogramMatchingImageFilter.hxx:257 narrow-scope/narrow-scope (call)
- BRAINSCommonLib/itkOtsuHistogramMatchingImageFilter.hxx:397 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSCommonLib/itkResampleInPlaceImageFilter.hxx:91 narrow-scope/narrow-scope (call)
- BRAINSConstellationDetector/TestSuite/LandmarksCompare.cxx:78 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSConstellationDetector/TestSuite/LandmarksCompare.cxx:80 narrow-scope/narrow-scope (side-effect)
- BRAINSConstellationDetector/TestSuite/TestlandmarksConstellationTrainingDefinitionIO.cxx:30 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSConstellationDetector/landmarkStatistics/GenerateAverageLmkFile.cxx:89 narrow-scope/narrow-scope (non-trivial)
- BRAINSConstellationDetector/landmarkStatistics/LmkStatistics.cxx:84 narrow-scope/narrow-scope (non-trivial)
- BRAINSConstellationDetector/landmarkStatistics/LmkStatistics.cxx:94 narrow-scope/narrow-scope (non-trivial)
- BRAINSConstellationDetector/src/BRAINSLinearModelerEPCA.cxx:69 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSConstellationDetector/src/BRAINSLinearModelerEPCA.cxx:172 narrow-scope/narrow-scope (call)
- BRAINSConstellationDetector/src/BRAINSLinearModelerEPCA.cxx:175 narrow-scope/narrow-scope (call)
- BRAINSConstellationDetector/src/BRAINSLinearModelerEPCA.cxx:191 narrow-scope/narrow-scope (call)
- BRAINSConstellationDetector/src/BRAINSLinearModelerEPCA.cxx:215 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSConstellationDetector/src/BRAINSLinearModelerEPCA.cxx:219 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSConstellationDetector/src/BRAINSLinearModelerEPCA.cxx:237 narrow-scope/narrow-scope (call)
- BRAINSConstellationDetector/src/BRAINSLmkTransform.cxx:121 narrow-scope/narrow-scope (call)
- BRAINSConstellationDetector/src/BRAINSLmkTransform.cxx:122 narrow-scope/narrow-scope (call)
- BRAINSConstellationDetector/src/BRAINSLmkTransform.cxx:123 narrow-scope/narrow-scope (call)
- BRAINSConstellationDetector/src/BRAINSLmkTransform.cxx:261 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSConstellationDetector/src/LLSModel.cxx:271 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSConstellationDetector/src/fcsv_to_hdf5.cxx:410 narrow-scope/narrow-scope (call)
- BRAINSConstellationDetector/src/fcsv_to_hdf5.cxx:535 narrow-scope/narrow-scope (call)
- BRAINSConstellationDetector/src/fcsv_to_hdf5.cxx:540 narrow-scope/narrow-scope (non-trivial)
- BRAINSConstellationDetector/src/fcsv_to_hdf5.cxx:560 narrow-scope/narrow-scope (call)
- BRAINSConstellationDetector/src/fcsv_to_hdf5.cxx:663 narrow-scope/narrow-scope (call)
- BRAINSConstellationDetector/src/fcsv_to_hdf5.cxx:680 narrow-scope/narrow-scope (non-trivial)
- BRAINSConstellationDetector/src/fcsv_to_hdf5.cxx:681 narrow-scope/narrow-scope (non-trivial)
- BRAINSConstellationDetector/src/fcsv_to_hdf5.cxx:682 narrow-scope/narrow-scope (non-trivial)
- BRAINSConstellationDetector/src/fcsv_to_hdf5.cxx:755 narrow-scope/narrow-scope (call)
- BRAINSConstellationDetector/src/insertMidACPCpoint.cxx:48 narrow-scope/narrow-scope (side-effect)
- BRAINSConstellationDetector/src/insertMidACPCpoint.cxx:49 narrow-scope/narrow-scope (side-effect)
- BRAINSDWICleanup/BRAINSDWICleanup.cxx:135 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSDWICleanup/BRAINSDWICleanup.cxx:136 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSDeface/BRAINSDeface.cxx:56 narrow-scope/narrow-scope (side-effect)
- BRAINSDeface/BRAINSDeface.cxx:57 narrow-scope/narrow-scope (call)
- BRAINSDeface/BRAINSDeface.cxx:58 narrow-scope/narrow-scope (call)
- BRAINSDeface/BRAINSDeface.cxx:152 narrow-scope/narrow-scope (side-effect)
- BRAINSDeface/BRAINSDeface.cxx:281 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSDeface/BRAINSDeface.cxx:321 narrow-scope/narrow-scope (non-trivial)
- BRAINSLabelStats/BRAINSLabelStats.cxx:96 narrow-scope/narrow-scope (non-trivial)
- BRAINSLabelStats/BRAINSLabelStats.cxx:99 narrow-scope/narrow-scope (non-trivial)
- BRAINSLabelStats/BRAINSLabelStats.cxx:101 narrow-scope/narrow-scope (non-trivial)
- BRAINSLabelStats/BRAINSLabelStats.cxx:103 narrow-scope/narrow-scope (non-trivial)
- BRAINSLabelStats/BRAINSLabelStats.cxx:105 narrow-scope/narrow-scope (non-trivial)
- BRAINSLabelStats/BRAINSLabelStats.cxx:111 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSLandmarkInitializer/BRAINSLandmarkInitializer.cxx:88 narrow-scope/narrow-scope (call)
- BRAINSLandmarkInitializer/BRAINSLandmarkInitializer.cxx:137 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSMultiModeSegment/BRAINSMultiModeSegment.cxx:114 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSMultiSTAPLE/BRAINSMultiSTAPLE.cxx:155 narrow-scope/narrow-scope (call)
- BRAINSMultiSTAPLE/BRAINSMultiSTAPLE.cxx:169 narrow-scope/narrow-scope (call)
- BRAINSMush/BRAINSMush.cxx:150 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSMush/itkMixtureStatisticCostFunction.hxx:38 narrow-scope/narrow-scope (non-trivial)
- BRAINSPosteriorToContinuousClass/BRAINSPosteriorToContinuousClass.cxx:172 narrow-scope/narrow-scope (side-effect)
- BRAINSPosteriorToContinuousClass/BRAINSPosteriorToContinuousClass.cxx:173 narrow-scope/narrow-scope (side-effect)
- BRAINSPosteriorToContinuousClass/BRAINSPosteriorToContinuousClass.cxx:174 narrow-scope/narrow-scope (side-effect)
- BRAINSPosteriorToContinuousClass/BRAINSPosteriorToContinuousClass.cxx:175 narrow-scope/narrow-scope (side-effect)
- BRAINSStripRotation/BRAINSStripRotation.cxx:166 narrow-scope/narrow-scope (side-effect)
- BRAINSSuperResolution/EdgeBasedWeightedTV/FFTWUpsample.cpp:354 narrow-scope/narrow-scope (call)
- BRAINSSuperResolution/EdgeBasedWeightedTV/FFTWUpsample.cpp:355 narrow-scope/narrow-scope (call)
- BRAINSSuperResolution/EdgeBasedWeightedTV/FFTWUpsample.cpp:562 narrow-scope/narrow-scope (call)
- BRAINSSuperResolution/EdgeBasedWeightedTV/FFTWUpsample.cpp:564 narrow-scope/narrow-scope (call)
- BRAINSSuperResolution/EdgeBasedWeightedTV/FFTWUpsampleTest.cpp:30 narrow-scope/narrow-scope (non-trivial)
- BRAINSSuperResolution/EdgeBasedWeightedTV/OpWeightedL2.cpp:34 narrow-scope/narrow-scope (call)
- BRAINSSuperResolution/EdgeBasedWeightedTV/OpWeightedL2.cpp:182 narrow-scope/narrow-scope (call)
- BRAINSSuperResolution/EdgeBasedWeightedTV/OpWeightedL2.cpp:184 narrow-scope/narrow-scope (call)
- BRAINSSuperResolution/EdgeBasedWeightedTV/SRElementwiseOps.h:90 narrow-scope/narrow-scope (call)
- BRAINSSuperResolution/EdgeBasedWeightedTV/SRElementwiseOps.h:91 narrow-scope/narrow-scope (call)
- BRAINSSuperResolution/EdgeBasedWeightedTV/TestSuite/SRElementwiseBenchmark.cxx:118 narrow-scope/narrow-scope (call)
- BRAINSSuperResolution/EdgeBasedWeightedTV/itkDivergenceImageFilter.hxx:105 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSSuperResolution/EdgeBasedWeightedTV/itkDivergenceImageFilter.hxx:203 narrow-scope/narrow-scope (non-trivial)
- BRAINSSuperResolution/EdgeBasedWeightedTV/itkDivergenceImageFilter.hxx:204 narrow-scope/narrow-scope (non-trivial)
- BRAINSSuperResolution/EdgeBasedWeightedTV/itkDivergenceImageFilter.hxx:217 narrow-scope/narrow-scope (call)
- BRAINSSuperResolution/EdgeBasedWeightedTV/itkDivergenceImageFilter.hxx:277 narrow-scope/narrow-scope (side-effect)
- BRAINSSuperResolution/GenerateEdgeMap/GenerateEdgeMapImage.cxx:141 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSTransformConvert/BRAINSTransformConvert.cxx:161 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSTransformConvert/BRAINSTransformConvert.cxx:198 narrow-scope/narrow-scope (nontrivial-dtor)
- BRAINSTransformConvert/BRAINSTransformConvert.cxx:321 narrow-scope/narrow-scope (nontrivial-dtor)
- ConvertBetweenFileFormats/castconvert.cxx:144 narrow-scope/narrow-scope (side-effect)
- ConvertBetweenFileFormats/castconvert.cxx:145 narrow-scope/narrow-scope (side-effect)
- ConvertBetweenFileFormats/castconverthelpers.h:76 narrow-scope/narrow-scope (call)
- ConvertBetweenFileFormats/castconverthelpers.h:87 narrow-scope/narrow-scope (call)
- DWIConvert/Convert4DImageTo3DSeries.cxx:41 narrow-scope/narrow-scope (call)
- DWIConvert/Convert4DImageTo3DSeries.cxx:66 narrow-scope/narrow-scope (call)
- DWIConvert/DWIConvertLib.cxx:291 narrow-scope/narrow-scope (nontrivial-dtor)
- DWIConvert/DWIConvertLib.cxx:517 narrow-scope/narrow-scope (nontrivial-dtor)
- DWIConvert/DWIConvertLib.cxx:542 narrow-scope/narrow-scope (nontrivial-dtor)
- DWIConvert/DWIConvertUtils.cxx:190 narrow-scope/narrow-scope (side-effect)
- DWIConvert/DWIConvertUtils.hxx:273 narrow-scope/narrow-scope (side-effect)
- DWIConvert/FSLDWIConverter.cxx:30 narrow-scope/narrow-scope (nontrivial-dtor)
- DWIConvert/GEDWIConverter.cxx:26 narrow-scope/narrow-scope (nontrivial-dtor)
- DWIConvert/GEDWIConverter.cxx:78 narrow-scope/narrow-scope (nontrivial-dtor)
- DWIConvert/GEDWIConverter.cxx:105 narrow-scope/narrow-scope (nontrivial-dtor)
- DWIConvert/NRRDDWIConverter.cxx:21 narrow-scope/narrow-scope (call)
- DWIConvert/NRRDDWIConverter.cxx:22 narrow-scope/narrow-scope (call)
- DWIConvert/NRRDDWIConverter.cxx:23 narrow-scope/narrow-scope (call)
- DWIConvert/NRRDDWIConverter.cxx:86 narrow-scope/narrow-scope (nontrivial-dtor)
- DWIConvert/PhilipsDWIConverter.cxx:159 narrow-scope/narrow-scope (non-trivial)
- DWIConvert/PhilipsDWIConverter.cxx:161 narrow-scope/narrow-scope (non-trivial)
- DWIConvert/PhilipsDWIConverter.cxx:208 narrow-scope/narrow-scope (side-effect)
- DWIConvert/PhilipsDWIConverter.cxx:260 narrow-scope/narrow-scope (side-effect)
- DWIConvert/TestSuite/BFileCompareTool.cpp:142 narrow-scope/narrow-scope (side-effect)
- DWIConvert/TestSuite/BFileCompareTool.cpp:143 narrow-scope/narrow-scope (side-effect)
- DWIConvert/TestSuite/BFileCompareTool.cpp:157 narrow-scope/narrow-scope (nontrivial-dtor)
- DWIConvert/TestSuite/BFileCompareTool.cpp:158 narrow-scope/narrow-scope (nontrivial-dtor)
- DWIConvert/TestSuite/DWICompare.cxx:127 narrow-scope/narrow-scope (side-effect)
- DWIConvert/TestSuite/DWICompare.cxx:168 narrow-scope/narrow-scope (call)
- DWIConvert/TestSuite/DWISimpleCompare.cxx:64 narrow-scope/narrow-scope (call)
- DWIConvert/TestSuite/NrrdToNIfTI.cxx:37 narrow-scope/narrow-scope (call)
- DWIConvert/TestSuite/NrrdToNIfTI.cxx:38 narrow-scope/narrow-scope (call)
- DWIConvert/TestSuite/NrrdToNIfTI.cxx:39 narrow-scope/narrow-scope (call)
- DWIConvert/TestSuite/NrrdToNIfTI.cxx:83 narrow-scope/narrow-scope (call)
- DWIConvert/TestSuite/checkTagValueInHeader.cxx:141 narrow-scope/narrow-scope (call)
- DWIConvert/TestSuite/checkTagValueInHeader.cxx:152 narrow-scope/narrow-scope (side-effect)
- DWIConvert/brainsDCMTKFileReader.cxx:71 narrow-scope/narrow-scope (nontrivial-dtor)
- DWIConvert/brainsDCMTKFileReader.cxx:88 narrow-scope/narrow-scope (nontrivial-dtor)
- DWIConvert/brainsDCMTKFileReader.cxx:215 narrow-scope/narrow-scope (nontrivial-dtor)
- DWIConvert/brainsDCMTKFileReader.cxx:342 narrow-scope/narrow-scope (nontrivial-dtor)
- DWIConvert/brainsDCMTKFileReader.cxx:370 narrow-scope/narrow-scope (nontrivial-dtor)
- DWIConvert/brainsDCMTKFileReader.cxx:405 narrow-scope/narrow-scope (nontrivial-dtor)
- DWIConvert/brainsDCMTKFileReader.cxx:437 narrow-scope/narrow-scope (nontrivial-dtor)
- DWIConvert/brainsDCMTKFileReader.cxx:471 narrow-scope/narrow-scope (nontrivial-dtor)
- DWIConvert/brainsDCMTKFileReader.cxx:504 narrow-scope/narrow-scope (nontrivial-dtor)
- DWIConvert/brainsDCMTKFileReader.cxx:519 narrow-scope/narrow-scope (nontrivial-dtor)
- DWIConvert/brainsDCMTKFileReader.cxx:553 narrow-scope/narrow-scope (nontrivial-dtor)
- DWIConvert/brainsDCMTKFileReader.cxx:613 narrow-scope/narrow-scope (nontrivial-dtor)
- DWIConvert/brainsDCMTKFileReader.cxx:638 narrow-scope/narrow-scope (nontrivial-dtor)
- DWIConvert/brainsDCMTKFileReader.cxx:665 narrow-scope/narrow-scope (nontrivial-dtor)
- DWIConvert/brainsDCMTKFileReader.cxx:714 narrow-scope/narrow-scope (nontrivial-dtor)
- DWIConvert/brainsDCMTKFileReader.cxx:748 narrow-scope/narrow-scope (nontrivial-dtor)
- DWIConvert/brainsDCMTKFileReader.cxx:777 narrow-scope/narrow-scope (nontrivial-dtor)
- DWIConvert/brainsDCMTKFileReader.cxx:843 narrow-scope/narrow-scope (nontrivial-dtor)
- DWIConvert/brainsDCMTKFileReader.cxx:874 narrow-scope/narrow-scope (nontrivial-dtor)
- DWIConvert/brainsDCMTKFileReader.cxx:890 narrow-scope/narrow-scope (nontrivial-dtor)
- DWIConvert/brainsDCMTKFileReader.cxx:921 narrow-scope/narrow-scope (nontrivial-dtor)
- DWIConvert/brainsDCMTKFileReader.cxx:937 narrow-scope/narrow-scope (nontrivial-dtor)
- DWIConvert/brainsDCMTKFileReader.cxx:961 narrow-scope/narrow-scope (nontrivial-dtor)
- DWIConvert/brainsDCMTKFileReader.cxx:1434 narrow-scope/narrow-scope (nontrivial-dtor)
- DWIConvert/brainsDCMTKFileReader.h:169 narrow-scope/narrow-scope (call)
- DWIConvert/brainsDCMTKFileReader.h:296 narrow-scope/narrow-scope (side-effect)
- GTRACT/Cmdline/compareTractInclusion.cxx:170 narrow-scope/narrow-scope (side-effect)
- GTRACT/Cmdline/compareTractInclusion.cxx:171 narrow-scope/narrow-scope (side-effect)
- GTRACT/Cmdline/gtractAverageBvalues.cxx:222 narrow-scope/narrow-scope (call)
- GTRACT/Cmdline/gtractAverageBvalues.cxx:272 narrow-scope/narrow-scope (non-trivial)
- GTRACT/Cmdline/gtractConcatDwi.cxx:111 narrow-scope/narrow-scope (non-trivial)
- GTRACT/Cmdline/gtractConcatDwi.cxx:161 narrow-scope/narrow-scope (call)
- GTRACT/Cmdline/gtractCoregBvalues.cxx:165 narrow-scope/narrow-scope (call)
- GTRACT/Cmdline/gtractCoregBvalues.cxx:167 narrow-scope/narrow-scope (call)
- GTRACT/Cmdline/gtractCoregBvalues.cxx:169 narrow-scope/narrow-scope (call)
- GTRACT/Cmdline/gtractCoregBvalues.cxx:171 narrow-scope/narrow-scope (call)
- GTRACT/Cmdline/gtractCoregBvalues.cxx:190 narrow-scope/narrow-scope (non-trivial)
- GTRACT/Cmdline/gtractCreateGuideFiber.cxx:103 narrow-scope/narrow-scope (call)
- GTRACT/Cmdline/gtractInvertBSplineTransform.cxx:95 narrow-scope/narrow-scope (nontrivial-dtor)
- GTRACT/Cmdline/gtractInvertRigidTransform.cxx:71 narrow-scope/narrow-scope (side-effect)
- GTRACT/Cmdline/gtractResampleAnisotropy.cxx:130 narrow-scope/narrow-scope (nontrivial-dtor)
- GTRACT/Cmdline/gtractResampleCodeImage.cxx:147 narrow-scope/narrow-scope (nontrivial-dtor)
- GTRACT/Common/algo.cxx:108 narrow-scope/narrow-scope (call)
- GTRACT/Common/algo.cxx:215 narrow-scope/narrow-scope (side-effect)
- GTRACT/Common/algo.cxx:218 narrow-scope/narrow-scope (side-effect)
- GTRACT/Common/itkComputeDiffusionTensorImageFilter.cxx:94 narrow-scope/narrow-scope (call)
- GTRACT/Common/itkComputeDiffusionTensorImageFilter.cxx:96 narrow-scope/narrow-scope (call)
- GTRACT/Common/itkComputeDiffusionTensorImageFilter.cxx:97 narrow-scope/narrow-scope (call)
- GTRACT/Common/itkComputeDiffusionTensorImageFilter.cxx:120 narrow-scope/narrow-scope (call)
- GTRACT/Common/itkComputeDiffusionTensorImageFilter.cxx:126 narrow-scope/narrow-scope (side-effect)
- GTRACT/Common/itkEigenVectorToColorImageFilter.cxx:78 narrow-scope/narrow-scope (side-effect)
- GTRACT/Common/itkGtractInverseDisplacementFieldImageFilter.hxx:164 narrow-scope/narrow-scope (non-trivial)
- GTRACT/Common/itkGtractInverseDisplacementFieldImageFilter.hxx:224 narrow-scope/narrow-scope (non-trivial)
- GTRACT/Common/itkGtractInverseDisplacementFieldImageFilter.hxx:229 narrow-scope/narrow-scope (call)
- GTRACT/Common/itkGtractParameterIO.cxx:56 narrow-scope/narrow-scope (nontrivial-dtor)
- GTRACT/Common/itkTensorToAnisotropyImageFilter.cxx:113 narrow-scope/narrow-scope (side-effect)
- GTRACT/Common/itkTensorToAnisotropyImageFilter.cxx:134 narrow-scope/narrow-scope (side-effect)
- GTRACT/Common/itkTensorToAnisotropyImageFilter.cxx:184 narrow-scope/narrow-scope (non-trivial)
- GTRACT/Common/itkTensorToAnisotropyImageFilter.cxx:199 narrow-scope/narrow-scope (nontrivial-dtor)
- GTRACT/Common/itkTensorToAnisotropyImageFilter.cxx:206 narrow-scope/narrow-scope (non-trivial)
- ImageCalculator/ImageCalculatorTemplates.h:846 narrow-scope/narrow-scope (nontrivial-dtor)
- ImageCalculator/ImageCalculatorUtils.cxx:334 narrow-scope/narrow-scope (nontrivial-dtor)
- ImageCalculator/ImageCalculatorUtils.cxx:343 narrow-scope/narrow-scope (nontrivial-dtor)
- ImageCalculator/ImageGenerate.cxx:76 narrow-scope/narrow-scope (nontrivial-dtor)

### gate-failed (120)

- BRAINSABC/brainseg/BRAINSABCUtilities.cxx:216 narrow-scope/narrow-scope
- BRAINSABC/brainseg/BRAINSABCUtilities.h:112 narrow-scope/narrow-scope
- BRAINSABC/brainseg/BRAINSABCUtilities.hxx:34 narrow-scope/uncovered
- BRAINSABC/brainseg/BRAINSABCUtilities.hxx:34 narrow-scope/narrow-scope
- BRAINSABC/brainseg/BRAINSABCUtilities.hxx:150 narrow-scope/narrow-scope
- BRAINSABC/brainseg/BRAINSABCUtilities.hxx:165 narrow-scope/narrow-scope
- BRAINSABC/brainseg/ComputeDistributions.h:159 narrow-scope/narrow-scope
- BRAINSABC/brainseg/ComputeDistributions.h:165 narrow-scope/narrow-scope
- BRAINSABC/brainseg/ComputeDistributions.h:290 narrow-scope/narrow-scope
- BRAINSABC/brainseg/EMSegmentationFilter.hxx:482 local-init/stream_open
- BRAINSABC/brainseg/EMSegmentationFilter.hxx:1706 local-init/sized_ctor
- BRAINSABC/brainseg/EMSegmentationFilter.hxx:2352 local-init/elem_diff
- BRAINSABC/brainseg/GeneratePurePlugMask.cxx:75 local-init/elem_diff
- BRAINSABC/brainseg/GeneratePurePlugMask.h:232 local-init/elem_diff
- BRAINSABC/brainseg/LLSBiasCorrector.hxx:78 member-init/prefer-member-initializer
- BRAINSABC/brainseg/LLSBiasCorrector.hxx:81 member-init/uncovered
- BRAINSABC/brainseg/OutputVolumeTemplate.h:45 narrow-scope/narrow-scope
- BRAINSABC/brainseg/OutputVolumeTemplate.h:50 narrow-scope/narrow-scope
- BRAINSABC/brainseg/PosteriorFilenameTemplate.h:37 narrow-scope/narrow-scope
- BRAINSABC/brainseg/PosteriorFilenameTemplate.h:42 narrow-scope/narrow-scope
- BRAINSABC/brainseg/itkIntegrityMetricMembershipFunction.hxx:35 member-init/prefer-member-initializer
- BRAINSABC/brainseg/itkIntegrityMetricMembershipFunction.hxx:36 member-init/uncovered
- BRAINSABC/brainseg/itkIntegrityMetricMembershipFunction.hxx:44 member-init/uncovered
- BRAINSCommonLib/BRAINSFitHelper.h:386 narrow-scope/narrow-scope
- BRAINSCommonLib/BRAINSFitHelperTemplate.hxx:328 narrow-scope/uncovered
- BRAINSCommonLib/BRAINSFitHelperTemplate.hxx:328 narrow-scope/narrow-scope
- BRAINSCommonLib/BRAINSFitSyN.h:156 narrow-scope/uncovered
- BRAINSCommonLib/BRAINSFitSyN.h:156 narrow-scope/narrow-scope
- BRAINSCommonLib/BRAINSFitSyN.h:161 narrow-scope/narrow-scope
- BRAINSCommonLib/BRAINSFitSyN.h:163 narrow-scope/narrow-scope
- BRAINSCommonLib/BRAINSFitSyN.h:163 narrow-scope/narrow-scope
- BRAINSCommonLib/BRAINSFitUtils.h:120 narrow-scope/narrow-scope
- BRAINSCommonLib/BRAINSFitUtils.h:132 narrow-scope/narrow-scope
- BRAINSCommonLib/BRAINSFitUtils.h:185 narrow-scope/uncovered
- BRAINSCommonLib/BRAINSFitUtils.h:185 narrow-scope/narrow-scope
- BRAINSCommonLib/BRAINSFitUtils.h:242 narrow-scope/narrow-scope
- BRAINSCommonLib/TestSuite/ConvertToRigidAffineGTest.cxx:74 local-init/elem_diff
- BRAINSCommonLib/TestSuite/ConvertToRigidAffineGTest.cxx:107 local-init/elem_diff
- BRAINSCommonLib/TestSuite/ConvertToRigidAffineGTest.cxx:145 local-init/elem_diff
- BRAINSCommonLib/TestSuite/ConvertToRigidAffineGTest.cxx:149 local-init/elem_diff
- BRAINSCommonLib/TestSuite/ConvertToRigidAffineGTest.cxx:195 local-init/elem_diff
- BRAINSCommonLib/TestSuite/ConvertToRigidAffineGTest.cxx:200 local-init/elem_diff
- BRAINSCommonLib/TestSuite/ConvertToRigidAffineGTest.cxx:204 local-init/elem_diff
- BRAINSCommonLib/TestSuite/ConvertToRigidAffineGTest.cxx:247 local-init/elem_diff
- BRAINSCommonLib/TestSuite/DWIMetaDataDictionaryValidatorTest.cxx:22 narrow-scope/narrow-scope
- BRAINSCommonLib/TestSuite/DWIMetaDataDictionaryValidatorTest.cxx:33 narrow-scope/narrow-scope
- BRAINSCommonLib/TestSuite/DWIMetaDataDictionaryValidatorTest.cxx:280 narrow-scope/narrow-scope
- BRAINSCommonLib/TestSuite/Slicer3LandmarkIOGTest.cxx:74 local-init/elem_diff
- BRAINSCommonLib/TestSuite/Slicer3LandmarkIOGTest.cxx:77 local-init/elem_diff
- BRAINSCommonLib/TestSuite/Slicer3LandmarkIOGTest.cxx:105 local-init/elem_diff
- BRAINSCommonLib/TestSuite/Slicer3LandmarkIOGTest.cxx:108 local-init/elem_diff
- BRAINSCommonLib/TestSuite/Slicer3LandmarkIOGTest.cxx:136 local-init/elem_diff
- BRAINSCommonLib/genericRegistrationHelper.h:104 narrow-scope/narrow-scope
- BRAINSCommonLib/genericRegistrationHelper.h:127 narrow-scope/narrow-scope
- BRAINSCommonLib/itkFindCenterOfBrainFilter.hxx:236 narrow-scope/narrow-scope
- BRAINSCommonLib/itkOtsuHistogramMatchingImageFilter.hxx:198 narrow-scope/narrow-scope
- BRAINSCommonLib/itkOtsuHistogramMatchingImageFilter.hxx:210 narrow-scope/narrow-scope
- BRAINSCommonLib/itkOtsuHistogramMatchingImageFilter.hxx:222 narrow-scope/narrow-scope
- BRAINSCommonLib/itkOtsuHistogramMatchingImageFilter.hxx:304 narrow-scope/narrow-scope
- BRAINSCommonLib/itkOtsuHistogramMatchingImageFilter.hxx:307 narrow-scope/uncovered
- BRAINSConstellationDetector/src/BRAINSConstellationDetector.cxx:152 local-init/stream_open
- BRAINSConstellationDetector/src/BRAINSConstellationModeler.cxx:178 local-init/stream_open
- BRAINSConstellationDetector/src/BRAINSHoughEyeDetector.hxx:76 local-init/elem_diff
- BRAINSConstellationDetector/src/BRAINSTransformFromFiducials.cxx:49 local-init/elem_diff
- BRAINSConstellationDetector/src/BinaryMaskEditorBasedOnLandmarks.cxx:50 local-init/elem_diff
- BRAINSConstellationDetector/src/BinaryMaskEditorBasedOnLandmarks.cxx:55 local-init/elem_diff
- BRAINSConstellationDetector/src/itkReflectiveCorrelationCenterToImageMetric.h:268 local-init/stream_open
- BRAINSConstellationDetector/src/itkReflectiveCorrelationCenterToImageMetric.h:391 local-init/elem_diff
- BRAINSConstellationDetector/src/landmarkIO.cxx:90 local-init/elem_diff
- BRAINSConstellationDetector/src/landmarkIO.cxx:835 local-init/stream_open
- BRAINSConstellationDetector/src/landmarksConstellationCommon.cxx:624 local-init/assign
- BRAINSConstellationDetector/src/landmarksConstellationCommon.h:249 local-init/assign
- BRAINSConstellationDetector/src/landmarksConstellationDetector.cxx:346 local-init/elem_diff
- BRAINSConstellationDetector/src/landmarksConstellationDetector.cxx:348 local-init/elem_diff
- BRAINSConstellationDetector/src/landmarksConstellationDetector.cxx:355 local-init/elem_diff
- BRAINSConstellationDetector/src/landmarksConstellationDetector.cxx:360 local-init/elem_diff
- BRAINSConstellationDetector/src/landmarksConstellationDetector.cxx:368 local-init/elem_diff
- BRAINSConstellationDetector/src/landmarksConstellationDetector.cxx:403 local-init/assign
- BRAINSConstellationDetector/src/landmarksConstellationDetector.cxx:480 local-init/elem_diff
- BRAINSConstellationDetector/src/landmarksConstellationDetector.cxx:508 local-init/elem_diff
- BRAINSConstellationDetector/src/landmarksConstellationModelIO.h:64 local-init/elem_diff
- BRAINSFit/TestSuite/CenterOfROIInitTest.cxx:63 local-init/elem_diff
- BRAINSInitializedControlPoints/BRAINSInitializedControlPoints.cxx:118 local-init/elem_diff
- BRAINSInitializedControlPoints/BRAINSInitializedControlPoints.cxx:141 local-init/elem_diff
- BRAINSResample/BRAINSResample.cxx:434 local-init/elem_diff
- BRAINSSnapShotWriter/BRAINSSnapShotWriter.cxx:178 local-init/elem_diff
- BRAINSSnapShotWriter/BRAINSSnapShotWriter.cxx:468 local-init/elem_diff
- BRAINSSuperResolution/EdgeBasedWeightedTV/TestSuite/SRElementwiseOpsGTest.cxx:96 local-init/elem_diff
- BRAINSSuperResolution/EdgeBasedWeightedTV/TestSuite/SRElementwiseOpsGTest.cxx:113 local-init/elem_diff
- BRAINSSuperResolution/EdgeBasedWeightedTV/TestSuite/SRElementwiseOpsGTest.cxx:114 local-init/elem_diff
- BRAINSTransformConvert/TestSuite/BRAINSTransformConvertMakeTestFiles.cxx:84 local-init/elem_diff
- BRAINSTransformConvert/TestSuite/BRAINSTransformConvertMakeTestFiles.cxx:97 local-init/elem_diff
- DWIConvert/DWIConvertUtils.h:96 local-init/stream_open
- DWIConvert/DWIConverter.cxx:521 local-init/elem_diff
- DWIConvert/DWIConverter.cxx:580 local-init/elem_diff
- DWIConvert/DWIDICOMConverterBase.cxx:82 local-init/elem_diff
- DWIConvert/DWIDICOMConverterBase.cxx:91 local-init/elem_diff
- DWIConvert/SiemensDWIConverter.cxx:76 local-init/assign
- DWIConvert/SiemensDWIConverter.cxx:448 local-init/elem_diff
- DWIConvert/SiemensDWIConverter.cxx:456 local-init/elem_diff
- GTRACT/Cmdline/TestSuite/GTRACTInvertRigidGTest.cxx:80 local-init/elem_diff
- GTRACT/Cmdline/gtractResampleDWIInPlace.cxx:289 local-init/stream_open
- GTRACT/Cmdline/gtractResampleDWIInPlace.cxx:392 local-init/elem_diff
- GTRACT/Cmdline/gtractResampleFibers.cxx:226 local-init/elem_diff
- GTRACT/Cmdline/gtractTensor.cxx:80 local-init/elem_diff
- GTRACT/Cmdline/gtractTensor.cxx:253 local-init/elem_diff
- GTRACT/Cmdline/gtractTensor.cxx:283 local-init/elem_diff
- GTRACT/Common/itkAnatomicalBSplineFilter.cxx:51 member-init/prefer-member-initializer
- GTRACT/Common/itkAnatomicalBSplineFilter.cxx:52 member-init/uncovered
- GTRACT/Common/itkAnatomicalBSplineFilter.cxx:60 member-init/uncovered
- GTRACT/Common/itkAnatomicalBSplineFilter.cxx:73 member-init/prefer-member-initializer
- GTRACT/Common/itkAnatomicalBSplineFilter.cxx:74 member-init/prefer-member-initializer
- GTRACT/Common/itkDtiFastMarchingCostFilter.hxx:69 member-init/prefer-member-initializer
- GTRACT/Common/itkDtiFastMarchingCostFilter.hxx:82 member-init/uncovered
- GTRACT/Common/itkDtiFastMarchingCostFilter.hxx:93 member-init/prefer-member-initializer
- GTRACT/Common/itkDtiFastMarchingCostFilter.hxx:94 member-init/prefer-member-initializer
- GTRACT/Common/itkDtiFastMarchingCostFilter.hxx:94 member-init/uncovered
- GTRACT/Common/itkDtiFastMarchingCostFilter.hxx:97 member-init/uncovered
- GTRACT/Common/itkDtiTrackingFilterBase.hxx:103 local-init/elem_diff
- GTRACT/Common/itkInvertBSplineFilter.cxx:84 local-init/elem_diff

### goto-or-case (1)

- BRAINSSuperResolution/EdgeBasedWeightedTV/FFTWUpsampleTest.cpp:108 narrow-scope/narrow-scope

### init-list-ctor (3)

- BRAINSCommonLib/BRAINSFitSyN.h:148 container-list-init/push_back_run
- GTRACT/Cmdline/gtractCoRegAnatomy.cxx:258 container-list-init/push_back_run
- GTRACT/Cmdline/gtractCoregBvalues.cxx:174 container-list-init/push_back_run

### loop-carried (231)

- ARCHIVE/BRAINSTalairach/vtkTalairachConversion.cxx:739 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- BRAINSABC/brainseg/AtlasCropImageSource.hxx:284 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- BRAINSABC/brainseg/AtlasDefinition.cxx:282 narrow-scope/narrow-scope
- BRAINSABC/brainseg/AtlasRegistrationMethod.hxx:140 narrow-scope/narrow-scope
- BRAINSABC/brainseg/BRAINSABC.cxx:1051 local-init/bool_branch (by-ref-arg)
- BRAINSABC/brainseg/BRAINSABCUtilities.cxx:108 narrow-scope/narrow-scope
- BRAINSABC/brainseg/BRAINSABCUtilities.cxx:198 narrow-scope/narrow-scope
- BRAINSABC/brainseg/BRAINSABCUtilities.cxx:213 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- BRAINSABC/brainseg/BRAINSABCUtilities.hxx:41 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- BRAINSABC/brainseg/ComputeDistributions.h:247 narrow-scope/narrow-scope
- BRAINSABC/brainseg/ComputeDistributions.h:255 narrow-scope/narrow-scope
- BRAINSABC/brainseg/ComputeDistributions.h:265 narrow-scope/narrow-scope
- BRAINSABC/brainseg/ComputeDistributions.h:373 narrow-scope/narrow-scope
- BRAINSABC/brainseg/GenerateLabelMapFromProbabilityMap.cxx:103 narrow-scope/narrow-scope
- BRAINSABC/brainseg/GeneratePurePlugMask.h:208 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- BRAINSABC/brainseg/LLSBiasCorrector.hxx:367 narrow-scope/narrow-scope
- BRAINSABC/brainseg/LLSBiasCorrector.hxx:551 narrow-scope/narrow-scope (escapes)
- BRAINSABC/brainseg/LLSBiasCorrector.hxx:730 narrow-scope/narrow-scope
- BRAINSABC/brainseg/OutputVolumeTemplate.h:40 narrow-scope/narrow-scope
- BRAINSABC/brainseg/OutputVolumeTemplate.h:41 narrow-scope/narrow-scope
- BRAINSABC/brainseg/PosteriorFilenameTemplate.h:33 narrow-scope/narrow-scope
- BRAINSCommonLib/BRAINSComputeLabels.h:68 narrow-scope/narrow-scope
- BRAINSCommonLib/BRAINSComputeLabels.h:69 narrow-scope/narrow-scope
- BRAINSCommonLib/BRAINSComputeLabels.h:106 narrow-scope/narrow-scope (escapes)
- BRAINSCommonLib/BRAINSFitHelperTemplate.hxx:61 narrow-scope/narrow-scope
- BRAINSCommonLib/BRAINSFitHelperTemplate.hxx:291 narrow-scope/narrow-scope
- BRAINSCommonLib/BRAINSFitHelperTemplate.hxx:299 narrow-scope/narrow-scope
- BRAINSCommonLib/BRAINSFitHelperTemplate.hxx:623 narrow-scope/narrow-scope (escapes)
- BRAINSCommonLib/BRAINSFitHelperTemplate.hxx:1556 narrow-scope/narrow-scope (escapes)
- BRAINSCommonLib/BRAINSFitUtils.h:69 narrow-scope/narrow-scope (escapes)
- BRAINSCommonLib/BRAINSFitUtils.h:70 narrow-scope/narrow-scope (escapes)
- BRAINSCommonLib/BRAINSFitUtils.h:118 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- BRAINSCommonLib/BRAINSFitUtils.h:130 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- BRAINSCommonLib/BRAINSFitUtils.h:274 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- BRAINSCommonLib/DWIMetaDataDictionaryValidator.cxx:283 narrow-scope/narrow-scope (escapes)
- BRAINSCommonLib/DWIMetaDataDictionaryValidator.cxx:329 narrow-scope/narrow-scope
- BRAINSCommonLib/GenericTransformImage.cxx:483 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- BRAINSCommonLib/GenericTransformImage.hxx:255 narrow-scope/narrow-scope (escapes)
- BRAINSCommonLib/LinearRegressionIntensityMatching.h:137 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- BRAINSCommonLib/Slicer3LandmarkIO.cxx:126 narrow-scope/narrow-scope
- BRAINSCommonLib/Slicer3LandmarkIO.cxx:176 narrow-scope/narrow-scope
- BRAINSCommonLib/Slicer3LandmarkIO.cxx:180 narrow-scope/narrow-scope
- BRAINSCommonLib/Slicer3LandmarkIO.cxx:232 narrow-scope/narrow-scope
- BRAINSCommonLib/Slicer3LandmarkIO.cxx:246 narrow-scope/narrow-scope (escapes)
- BRAINSCommonLib/Slicer3LandmarkIO.cxx:257 narrow-scope/narrow-scope (escapes)
- BRAINSCommonLib/Slicer3LandmarkIO.cxx:325 narrow-scope/narrow-scope
- BRAINSCommonLib/Slicer3LandmarkIO.cxx:339 narrow-scope/narrow-scope (escapes)
- BRAINSCommonLib/Slicer3LandmarkIO.cxx:350 narrow-scope/narrow-scope (escapes)
- BRAINSCommonLib/Slicer3LandmarkWeightIO.cxx:32 narrow-scope/narrow-scope
- BRAINSCommonLib/TestSuite/AverageImageFilterGTest.cxx:77 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- BRAINSCommonLib/TestSuite/DWIMetaDataDictionaryValidatorTest.cxx:127 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- BRAINSCommonLib/TestSuite/ImgmathGTest.cxx:70 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- BRAINSCommonLib/TestSuite/ImgmathGTest.cxx:78 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- BRAINSCommonLib/TestSuite/ImgmathGTest.cxx:195 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- BRAINSCommonLib/TestSuite/ImgmathGTest.cxx:212 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- BRAINSCommonLib/TestSuite/itkIOGTest.cxx:68 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- BRAINSCommonLib/TestSuite/itkResampleInPlaceImageFilterTest.cxx:106 narrow-scope/narrow-scope (escapes)
- BRAINSCommonLib/TestSuite/itkResampleInPlaceImageFilterTest.cxx:125 narrow-scope/narrow-scope (escapes)
- BRAINSCommonLib/brainsiaTestingComparisonImageFilter.hxx:119 narrow-scope/narrow-scope (address-taken)
- BRAINSCommonLib/brainsiaTestingComparisonImageFilter.hxx:133 narrow-scope/narrow-scope
- BRAINSCommonLib/brainsiaTestingComparisonImageFilter.hxx:134 narrow-scope/narrow-scope
- BRAINSCommonLib/brainsiaTestingComparisonImageFilter.hxx:192 narrow-scope/narrow-scope (escapes)
- BRAINSCommonLib/brainsiaTestingComparisonImageFilter.hxx:229 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- BRAINSCommonLib/genericRegistrationHelper.h:124 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- BRAINSCommonLib/genericRegistrationHelper.hxx:202 narrow-scope/narrow-scope (escapes)
- BRAINSCommonLib/genericRegistrationHelper.hxx:217 narrow-scope/narrow-scope
- BRAINSCommonLib/itkAverageImageFilter.hxx:60 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- BRAINSCommonLib/itkBRAINSToolsTestMain.h:85 narrow-scope/narrow-scope
- BRAINSCommonLib/itkComputeHistogramQuantileThresholds.hxx:104 narrow-scope/narrow-scope (escapes)
- BRAINSCommonLib/itkComputeHistogramQuantileThresholds.hxx:111 narrow-scope/narrow-scope
- BRAINSCommonLib/itkFindCenterOfBrainFilter.hxx:123 narrow-scope/narrow-scope (escapes)
- BRAINSCommonLib/itkFindCenterOfBrainFilter.hxx:206 narrow-scope/narrow-scope (escapes)
- BRAINSCommonLib/itkFindCenterOfBrainFilter.hxx:214 narrow-scope/narrow-scope
- BRAINSCommonLib/itkFindCenterOfBrainFilter.hxx:215 narrow-scope/narrow-scope
- BRAINSCommonLib/itkFindCenterOfBrainFilter.hxx:216 narrow-scope/narrow-scope (escapes)
- BRAINSCommonLib/itkFindCenterOfBrainFilter.hxx:217 narrow-scope/narrow-scope (escapes)
- BRAINSCommonLib/itkFindCenterOfBrainFilter.hxx:374 narrow-scope/narrow-scope (escapes)
- BRAINSCommonLib/itkLargestForegroundFilledMaskImageFilter.hxx:123 narrow-scope/narrow-scope (escapes)
- BRAINSCommonLib/itkOtsuHistogramMatchingImageFilter.hxx:300 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- BRAINSCommonLib/itkV3TestKernel/include/itkRandomImageSource.hxx:240 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- BRAINSCommonLib/itkV3TestKernel/include/itkTestingComparisonImageFilter.hxx:227 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- BRAINSCommonLib/itkV3TestKernel/include/itkTestingExtractSliceImageFilter.hxx:291 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- BRAINSConstellationDetector/src/BRAINSConstellationLandmarksTransform.cxx:104 narrow-scope/narrow-scope (escapes)
- BRAINSConstellationDetector/src/BRAINSLinearModelerEPCA.cxx:89 narrow-scope/narrow-scope
- BRAINSConstellationDetector/src/BRAINSLinearModelerEPCA.cxx:104 narrow-scope/narrow-scope
- BRAINSConstellationDetector/src/BRAINSLinearModelerEPCA.cxx:134 narrow-scope/narrow-scope
- BRAINSConstellationDetector/src/BRAINSLinearModelerEPCA.cxx:140 narrow-scope/narrow-scope
- BRAINSConstellationDetector/src/BRAINSLinearModelerEPCA.cxx:146 narrow-scope/narrow-scope
- BRAINSConstellationDetector/src/BRAINSLinearModelerEPCA.cxx:192 narrow-scope/narrow-scope
- BRAINSConstellationDetector/src/BRAINSLinearModelerEPCA.cxx:198 narrow-scope/narrow-scope
- BRAINSConstellationDetector/src/BRAINSLinearModelerEPCA.cxx:271 narrow-scope/narrow-scope
- BRAINSConstellationDetector/src/BinaryMaskEditorBasedOnLandmarks.cxx:111 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- BRAINSConstellationDetector/src/BinaryMaskEditorBasedOnLandmarks.cxx:174 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- BRAINSConstellationDetector/src/ChopImageBelowLowerBound.h:64 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- BRAINSConstellationDetector/src/fcsv_to_hdf5.cxx:257 narrow-scope/narrow-scope
- BRAINSConstellationDetector/src/fcsv_to_hdf5.cxx:431 narrow-scope/narrow-scope
- BRAINSConstellationDetector/src/fcsv_to_hdf5.cxx:545 narrow-scope/narrow-scope
- BRAINSConstellationDetector/src/fcsv_to_hdf5.cxx:662 narrow-scope/narrow-scope (escapes)
- BRAINSConstellationDetector/src/fcsv_to_hdf5.cxx:774 narrow-scope/narrow-scope
- BRAINSConstellationDetector/src/insertMidACPCpoint.cxx:53 narrow-scope/narrow-scope
- BRAINSConstellationDetector/src/itkHoughTransformRadialVotingImageFilter.hxx:252 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- BRAINSConstellationDetector/src/itkHoughTransformRadialVotingImageFilter.hxx:419 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- BRAINSConstellationDetector/src/itkHoughTransformRadialVotingImageFilter.hxx:434 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- BRAINSConstellationDetector/src/landmarkIO.cxx:279 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- BRAINSConstellationDetector/src/landmarksConstellationCommon.cxx:145 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- BRAINSConstellationDetector/src/landmarksConstellationCommon.cxx:177 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- BRAINSConstellationDetector/src/landmarksConstellationTrainingDefinitionIO.h:114 narrow-scope/narrow-scope
- BRAINSConstellationDetector/src/landmarksDataSet.h:82 narrow-scope/narrow-scope
- BRAINSConstellationDetector/src/tempSphereFromAreaEstimates.cxx:146 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- BRAINSConstellationDetector/src/tempSphereFromAreaEstimates.cxx:416 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- BRAINSDWICleanup/BRAINSDWICleanup.cxx:139 narrow-scope/narrow-scope (escapes)
- BRAINSDWICleanup/BRAINSDWICleanup.cxx:154 narrow-scope/narrow-scope (escapes)
- BRAINSDeface/BRAINSDeface.cxx:146 narrow-scope/narrow-scope
- BRAINSDeface/BRAINSDeface.cxx:147 narrow-scope/narrow-scope
- BRAINSDeface/BRAINSDeface.cxx:150 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- BRAINSDeface/BRAINSDeface.cxx:278 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- BRAINSDeface/BRAINSDeface.cxx:308 narrow-scope/narrow-scope
- BRAINSDeface/BRAINSDeface.cxx:340 narrow-scope/narrow-scope
- BRAINSDeface/BRAINSDeface.cxx:343 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- BRAINSDeface/BRAINSDeface.cxx:355 narrow-scope/narrow-scope
- BRAINSDeface/BRAINSDeface.cxx:359 narrow-scope/narrow-scope
- BRAINSFit/BRAINSFit.cxx:276 narrow-scope/narrow-scope
- BRAINSFit/BRAINSFit.cxx:301 local-init/assign (gap-statement)
- BRAINSFit/BRAINSFit.cxx:302 local-init/assign (gap-statement)
- BRAINSFit/PerformMetricTest.cxx:152 narrow-scope/narrow-scope
- BRAINSFit/PerformMetricTest.cxx:156 narrow-scope/narrow-scope
- BRAINSLabelStats/BRAINSLabelStats.cxx:98 narrow-scope/narrow-scope (escapes)
- BRAINSLabelStats/BRAINSLabelStats.cxx:224 local-init/assign (gap-statement)
- BRAINSLabelStats/BRAINSLabelStats.cxx:225 local-init/assign (gap-statement)
- BRAINSLabelStats/BRAINSLabelStats.cxx:226 local-init/assign (gap-statement)
- BRAINSLabelStats/BRAINSLabelStats.cxx:227 local-init/assign (gap-statement)
- BRAINSLabelStats/BRAINSLabelStats.cxx:239 local-init/assign (gap-statement)
- BRAINSLabelStats/BRAINSLabelStats.cxx:240 local-init/assign (gap-statement)
- BRAINSLabelStats/BRAINSLabelStats.cxx:241 local-init/assign (gap-statement)
- BRAINSLabelStats/BRAINSLabelStats.cxx:242 local-init/assign (gap-statement)
- BRAINSLandmarkInitializer/BRAINSLandmarkInitializer.cxx:92 narrow-scope/narrow-scope (escapes)
- BRAINSLandmarkInitializer/BRAINSLandmarkInitializer.cxx:93 narrow-scope/narrow-scope (escapes)
- BRAINSMush/BRAINSMush.cxx:178 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- BRAINSMush/BRAINSMush.cxx:263 local-init/elem_diff (gap-statement)
- BRAINSMush/BRAINSMush.cxx:264 local-init/elem_diff (gap-statement)
- BRAINSMush/BRAINSMush.cxx:658 local-init/elem_diff (gap-statement)
- BRAINSMush/BRAINSMush.cxx:659 local-init/elem_diff (gap-statement)
- BRAINSMush/BRAINSMush.cxx:674 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- BRAINSMush/itkApplyMaskImageFilter.hxx:100 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- BRAINSPosteriorToContinuousClass/BRAINSPosteriorToContinuousClass.cxx:169 narrow-scope/narrow-scope
- BRAINSPosteriorToContinuousClass/BRAINSPosteriorToContinuousClass.cxx:170 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- BRAINSROIAuto/BRAINSROIAuto.cxx:108 narrow-scope/narrow-scope (escapes)
- BRAINSROIAuto/TestSuite/TestImage.cxx:77 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- BRAINSResample/BRAINSResample.cxx:305 local-init/assign (gap-statement)
- BRAINSResample/itkGridForwardWarpImageFilterNew.hxx:184 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- BRAINSSuperResolution/EdgeBasedWeightedTV/OpWeightedL2.cpp:37 narrow-scope/narrow-scope
- BRAINSSuperResolution/EdgeBasedWeightedTV/OpWeightedL2.cpp:191 narrow-scope/narrow-scope (escapes)
- BRAINSSuperResolution/EdgeBasedWeightedTV/SimpleOpWeightedL2.cpp:239 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- BRAINSSuperResolution/EdgeBasedWeightedTV/TestFFTW2D.cpp:69 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- BRAINSSuperResolution/EdgeBasedWeightedTV/TestSuite/SRElementwiseBenchmark.cxx:51 narrow-scope/narrow-scope (escapes)
- BRAINSSuperResolution/EdgeBasedWeightedTV/TestSuite/SRElementwiseBenchmark.cxx:52 narrow-scope/narrow-scope (escapes)
- BRAINSSuperResolution/EdgeBasedWeightedTV/TestSuite/SRElementwiseBenchmark.cxx:59 narrow-scope/narrow-scope
- BRAINSSuperResolution/EdgeBasedWeightedTV/TestSuite/SRElementwiseBenchmark.cxx:60 narrow-scope/narrow-scope
- BRAINSSuperResolution/EdgeBasedWeightedTV/itkDivergenceImageFilter.h:315 narrow-scope/narrow-scope
- BRAINSSuperResolution/EdgeBasedWeightedTV/itkDivergenceImageFilter.h:318 narrow-scope/narrow-scope (escapes)
- BRAINSSuperResolution/EdgeBasedWeightedTV/itkDivergenceImageFilter.hxx:202 narrow-scope/narrow-scope (address-taken)
- BRAINSSuperResolution/EdgeBasedWeightedTV/itkDivergenceImageFilter.hxx:326 narrow-scope/narrow-scope
- BRAINSSuperResolution/EdgeBasedWeightedTV/itkIdentityResampleByFFT.hxx:338 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- BRAINSSuperResolution/EdgeBasedWeightedTV/itkIdentityResampleByFFT.hxx:466 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- BRAINSTransformConvert/BRAINSTransformConvert.cxx:250 narrow-scope/narrow-scope (escapes)
- BRAINSTransformConvert/BRAINSTransformConvert.cxx:289 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- BRAINSTransformConvert/BRAINSTransformConvert.cxx:323 narrow-scope/narrow-scope (escapes)
- BRAINSTransformConvert/TestSuite/BRAINSTransformConvertMakeTestFiles.cxx:66 local-init/elem_diff (gap-statement)
- BRAINSTransformConvert/TestSuite/BRAINSTransformConvertMakeTestFiles.cxx:67 local-init/elem_diff (gap-statement)
- BRAINSTransformConvert/TestSuite/BRAINSTransformConvertMakeTestFiles.cxx:167 local-init/elem_diff (gap-statement)
- BRAINSTransformConvert/TestSuite/BRAINSTransformConvertMakeTestFiles.cxx:183 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- DWIConvert/DWIConvertUtils.cxx:103 narrow-scope/narrow-scope
- DWIConvert/DWIConvertUtils.hxx:168 narrow-scope/narrow-scope (address-taken)
- DWIConvert/DWIConvertUtils.hxx:183 narrow-scope/narrow-scope (address-taken)
- DWIConvert/NRRDDWIConverter.cxx:56 narrow-scope/narrow-scope
- DWIConvert/PhilipsDWIConverter.cxx:167 narrow-scope/narrow-scope
- DWIConvert/SiemensDWIConverter.cxx:496 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- DWIConvert/SiemensDWIConverter.h:93 narrow-scope/narrow-scope
- DWIConvert/TestSuite/DWISimpleCompare.cxx:52 narrow-scope/narrow-scope
- DWIConvert/TestSuite/DWISimpleCompare.cxx:118 narrow-scope/narrow-scope (escapes)
- DWIConvert/TestSuite/DWISimpleCompare.cxx:132 narrow-scope/narrow-scope
- DWIConvert/TestSuite/NrrdToNIfTI.cxx:69 narrow-scope/narrow-scope
- DWIConvert/TestSuite/SiemensBMatrixGTest.cxx:41 narrow-scope/narrow-scope (escapes)
- DWIConvert/brainsDCMTKFileReader.cxx:1310 narrow-scope/narrow-scope (escapes)
- DWIConvert/brainsDCMTKFileReader.cxx:1311 narrow-scope/narrow-scope (escapes)
- DWIConvert/brainsDCMTKFileReader.cxx:1312 narrow-scope/narrow-scope (escapes)
- GTRACT/Cmdline/extractNrrdVectorIndex.cxx:86 narrow-scope/narrow-scope (escapes)
- GTRACT/Cmdline/gtractAnisotropyMap.cxx:120 narrow-scope/narrow-scope
- GTRACT/Cmdline/gtractAnisotropyMap.cxx:122 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- GTRACT/Cmdline/gtractAverageBvalues.cxx:105 narrow-scope/narrow-scope (escapes)
- GTRACT/Cmdline/gtractAverageBvalues.cxx:188 narrow-scope/narrow-scope
- GTRACT/Cmdline/gtractAverageBvalues.cxx:196 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- GTRACT/Cmdline/gtractAverageBvalues.cxx:208 narrow-scope/narrow-scope (escapes)
- GTRACT/Cmdline/gtractAverageBvalues.cxx:227 narrow-scope/narrow-scope
- GTRACT/Cmdline/gtractAverageBvalues.cxx:303 narrow-scope/narrow-scope
- GTRACT/Cmdline/gtractClipAnisotropy.cxx:84 narrow-scope/narrow-scope (escapes)
- GTRACT/Cmdline/gtractClipAnisotropy.cxx:122 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- GTRACT/Cmdline/gtractCoRegAnatomy.cxx:134 narrow-scope/narrow-scope (escapes)
- GTRACT/Cmdline/gtractConcatDwi.cxx:94 narrow-scope/narrow-scope (escapes)
- GTRACT/Cmdline/gtractConcatDwi.cxx:118 narrow-scope/narrow-scope
- GTRACT/Cmdline/gtractConcatDwi.cxx:119 narrow-scope/narrow-scope
- GTRACT/Cmdline/gtractConcatDwi.cxx:121 narrow-scope/narrow-scope
- GTRACT/Cmdline/gtractCopyImageOrientation.cxx:85 narrow-scope/narrow-scope (escapes)
- GTRACT/Cmdline/gtractCoregBvalues.cxx:63 narrow-scope/narrow-scope
- GTRACT/Cmdline/gtractCoregBvalues.cxx:163 local-init/assign (gap-statement)
- GTRACT/Cmdline/gtractCoregBvalues.cxx:189 narrow-scope/narrow-scope (escapes)
- GTRACT/Cmdline/gtractCoregBvalues.cxx:295 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- GTRACT/Cmdline/gtractImageConformity.cxx:85 narrow-scope/narrow-scope (escapes)
- GTRACT/Cmdline/gtractResampleB0.cxx:97 narrow-scope/narrow-scope (escapes)
- GTRACT/Cmdline/gtractResampleCodeImage.cxx:163 local-init/assign (gap-statement)
- GTRACT/Common/algo.cxx:87 local-init/assign (gap-statement)
- GTRACT/Common/algo.cxx:211 narrow-scope/narrow-scope (escapes)
- GTRACT/Common/itkAnatomicalBSplineFilter.cxx:107 local-init/assign (gap-statement)
- GTRACT/Common/itkDtiFastMarchingCostFilter.hxx:270 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- GTRACT/Common/itkDtiFastMarchingCostFilter.hxx:281 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- GTRACT/Common/itkDtiFastMarchingCostFilter.hxx:328 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- GTRACT/Common/itkDtiFastMarchingCostFilter.hxx:823 local-init/assign (gap-statement)
- GTRACT/Common/itkDtiGraphSearchTrackingFilter.hxx:370 local-init/assign (gap-statement)
- GTRACT/Common/itkDtiGraphSearchTrackingFilter.hxx:372 local-init/assign (gap-statement)
- GTRACT/Common/itkDtiGraphSearchTrackingFilter.hxx:374 local-init/assign (gap-statement)
- GTRACT/Common/itkEigenVectorToColorImageFilter.cxx:75 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- GTRACT/Common/itkGtractInverseDeformationFieldImageFilter.hxx:238 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- GTRACT/Common/itkGtractInverseDisplacementFieldImageFilter.hxx:157 narrow-scope/narrow-scope
- GTRACT/Common/itkGtractInverseDisplacementFieldImageFilter.hxx:163 narrow-scope/narrow-scope (escapes)
- GTRACT/Common/itkGtractInverseDisplacementFieldImageFilter.hxx:234 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- GTRACT/Common/itkGtractInverseDisplacementFieldImageFilter.hxx:241 narrow-scope/narrow-scope (escapes)
- GTRACT/Common/itkInvertBSplineFilter.cxx:83 local-init/assign (gap-statement)
- GTRACT/Common/itkTensorToAnisotropyImageFilter.cxx:110 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- GTRACT/Common/itkTensorToAnisotropyImageFilter.cxx:131 itk-helpers/fillbuffer-over-iterate (not-fill-shape)
- ImageCalculator/ImageCalculatorTemplates.h:618 narrow-scope/narrow-scope
- ImageCalculator/ImageCalculatorUtils.cxx:48 narrow-scope/narrow-scope (escapes)

### preprocessor (8)

- BRAINSSuperResolution/EdgeBasedWeightedTV/FFTWUpsampleTest.cpp:78 local-const/const
- BRAINSSuperResolution/EdgeBasedWeightedTV/OpWeightedL2.cpp:148 narrow-scope/narrow-scope
- BRAINSSuperResolution/EdgeBasedWeightedTV/OpWeightedL2.cpp:153 narrow-scope/narrow-scope
- BRAINSSuperResolution/EdgeBasedWeightedTV/OpWeightedL2.cpp:154 narrow-scope/narrow-scope
- BRAINSSuperResolution/EdgeBasedWeightedTV/OpWeightedL2.cpp:156 narrow-scope/narrow-scope
- BRAINSSuperResolution/EdgeBasedWeightedTV/OpWeightedL2.cpp:157 narrow-scope/narrow-scope
- BRAINSSuperResolution/EdgeBasedWeightedTV/OpWeightedL2.cpp:158 narrow-scope/narrow-scope
- BRAINSSuperResolution/EdgeBasedWeightedTV/OpWeightedL2.cpp:160 narrow-scope/narrow-scope

### static-local (1)

- BRAINSCommonLib/genericRegistrationHelper.h:293 narrow-scope/narrow-scope

### try-read-after (63)

- BRAINSABC/TestSuite/AtlasDefinitionGTest.cxx:161 narrow-scope/narrow-scope
- BRAINSABC/brainseg/AtlasDefinition.cxx:258 narrow-scope/narrow-scope
- BRAINSCommonLib/BRAINSFitHelperTemplate.hxx:595 narrow-scope/narrow-scope
- BRAINSCommonLib/BRAINSFitHelperTemplate.hxx:800 narrow-scope/narrow-scope
- BRAINSCommonLib/BRAINSFitHelperTemplate.hxx:878 narrow-scope/narrow-scope
- BRAINSCommonLib/BRAINSFitHelperTemplate.hxx:964 narrow-scope/narrow-scope
- BRAINSCommonLib/BRAINSFitHelperTemplate.hxx:1055 narrow-scope/narrow-scope
- BRAINSCommonLib/GenericTransformImage.cxx:159 narrow-scope/narrow-scope
- BRAINSCommonLib/GenericTransformImage.cxx:271 narrow-scope/narrow-scope
- BRAINSCommonLib/GenericTransformImage.cxx:275 narrow-scope/narrow-scope
- BRAINSCommonLib/TestSuite/DWIMetaDataDictionaryValidatorTest.cxx:148 narrow-scope/narrow-scope
- BRAINSCommonLib/TestSuite/DWIMetaDataDictionaryValidatorTest.cxx:161 narrow-scope/narrow-scope
- BRAINSCommonLib/TestSuite/DWIMetaDataDictionaryValidatorTest.cxx:164 narrow-scope/narrow-scope
- BRAINSCommonLib/TestSuite/LocaleSafeConversionsGTest.cxx:122 narrow-scope/narrow-scope
- BRAINSCommonLib/TestSuite/LocaleSafeConversionsGTest.cxx:490 narrow-scope/narrow-scope
- BRAINSCommonLib/itkBRAINSToolsTestMain.h:193 narrow-scope/narrow-scope
- BRAINSCommonLib/itkBRAINSToolsTestMain.h:194 narrow-scope/narrow-scope
- BRAINSCreateLabelMapFromProbabilityMaps/BRAINSCreateLabelMapFromProbabilityMaps.cxx:50 narrow-scope/narrow-scope
- BRAINSCreateLabelMapFromProbabilityMaps/BRAINSCreateLabelMapFromProbabilityMaps.cxx:115 narrow-scope/narrow-scope
- BRAINSCreateLabelMapFromProbabilityMaps/BRAINSCreateLabelMapFromProbabilityMaps.cxx:116 narrow-scope/narrow-scope
- BRAINSFit/PerformMetricTest.cxx:175 narrow-scope/narrow-scope
- BRAINSFit/PerformMetricTest.cxx:176 narrow-scope/narrow-scope
- BRAINSMultiSTAPLE/BRAINSMultiSTAPLE.cxx:82 narrow-scope/narrow-scope
- BRAINSMultiSTAPLE/BRAINSMultiSTAPLE.cxx:109 narrow-scope/narrow-scope
- BRAINSMultiSTAPLE/BRAINSMultiSTAPLE.cxx:181 narrow-scope/narrow-scope
- BRAINSMultiSTAPLE/BRAINSMultiSTAPLE.cxx:196 narrow-scope/narrow-scope
- BRAINSMultiSTAPLE/BRAINSMultiSTAPLE.cxx:257 narrow-scope/narrow-scope
- BRAINSMush/BRAINSMush.cxx:431 narrow-scope/narrow-scope
- BRAINSMush/BRAINSMush.cxx:507 narrow-scope/narrow-scope
- BRAINSMush/BRAINSMush.cxx:508 narrow-scope/narrow-scope
- BRAINSPosteriorToContinuousClass/BRAINSPosteriorToContinuousClass.cxx:91 narrow-scope/narrow-scope
- BRAINSPosteriorToContinuousClass/BRAINSPosteriorToContinuousClass.cxx:92 narrow-scope/narrow-scope
- BRAINSPosteriorToContinuousClass/BRAINSPosteriorToContinuousClass.cxx:93 narrow-scope/narrow-scope
- BRAINSPosteriorToContinuousClass/BRAINSPosteriorToContinuousClass.cxx:94 narrow-scope/narrow-scope
- BRAINSPosteriorToContinuousClass/BRAINSPosteriorToContinuousClass.cxx:95 narrow-scope/narrow-scope
- BRAINSPosteriorToContinuousClass/BRAINSPosteriorToContinuousClass.cxx:96 narrow-scope/narrow-scope
- BRAINSPosteriorToContinuousClass/BRAINSPosteriorToContinuousClass.cxx:97 narrow-scope/narrow-scope
- BRAINSPosteriorToContinuousClass/BRAINSPosteriorToContinuousClass.cxx:100 narrow-scope/narrow-scope
- BRAINSPosteriorToContinuousClass/BRAINSPosteriorToContinuousClass.cxx:101 narrow-scope/narrow-scope
- BRAINSPosteriorToContinuousClass/BRAINSPosteriorToContinuousClass.cxx:102 narrow-scope/narrow-scope
- BRAINSPosteriorToContinuousClass/BRAINSPosteriorToContinuousClass.cxx:103 narrow-scope/narrow-scope
- BRAINSPosteriorToContinuousClass/BRAINSPosteriorToContinuousClass.cxx:104 narrow-scope/narrow-scope
- BRAINSPosteriorToContinuousClass/BRAINSPosteriorToContinuousClass.cxx:105 narrow-scope/narrow-scope
- BRAINSPosteriorToContinuousClass/BRAINSPosteriorToContinuousClass.cxx:106 narrow-scope/narrow-scope
- BRAINSResample/BRAINSResize.cxx:61 narrow-scope/narrow-scope
- BRAINSStripRotation/BRAINSStripRotation.cxx:54 narrow-scope/narrow-scope
- BRAINSTransformConvert/TestSuite/ImageCompare.cxx:31 narrow-scope/narrow-scope
- BRAINSTransformConvert/TestSuite/ImageCompare.cxx:33 narrow-scope/narrow-scope
- BRAINSTransformConvert/TestSuite/ImageCompare.cxx:37 narrow-scope/narrow-scope
- BRAINSTransformConvert/TestSuite/ImageCompare.cxx:39 narrow-scope/narrow-scope
- ConvertBetweenFileFormats/castconvert.cxx:128 narrow-scope/narrow-scope
- DWIConvert/DWIConvertLib.cxx:84 narrow-scope/narrow-scope
- DWIConvert/DWIConvertLib.cxx:106 narrow-scope/narrow-scope
- DWIConvert/DWIConvertLib.cxx:219 narrow-scope/narrow-scope
- DWIConvert/DWIConvertLib.cxx:220 narrow-scope/narrow-scope
- DWIConvert/PhilipsDWIConverter.cxx:222 narrow-scope/narrow-scope
- DWIConvert/PhilipsDWIConverter.cxx:241 narrow-scope/narrow-scope
- DWIConvert/TestSuite/DWICompare.cxx:218 narrow-scope/narrow-scope
- DWIConvert/TestSuite/DWICompare.cxx:219 narrow-scope/narrow-scope
- DWIConvert/TestSuite/DWISimpleCompare.cxx:255 narrow-scope/narrow-scope
- DWIConvert/TestSuite/DWISimpleCompare.cxx:256 narrow-scope/narrow-scope
- GTRACT/Cmdline/gtractTransformToDisplacementField.cxx:74 narrow-scope/narrow-scope
- GTRACT/Common/itkAnatomicalBSplineFilter.cxx:172 narrow-scope/narrow-scope

## Build

- pre-commit: passed
- Full build: pass

### Pre-existing warnings in touched files

Outside every changed hunk; listed for review, not counted against the run.

- `BRAINSCommonLib/TestSuite/itkIOGTest.cxx:156: warning: unused parameter 'y' [-Wunused-parameter]`
- `BRAINSCommonLib/TestSuite/itkIOGTest.cxx:156: warning: unused parameter 'z' [-Wunused-parameter]`

Warnings in the rebuild log:

> /Users/johnsonhj/src/BRAINSTools/GTRACT/Common/itkAnatomicalBSplineFilter.cxx:104:23: warning: unused variable 'bsplineRegion' [-Wunused-variable]
> /Users/johnsonhj/src/BRAINSTools/BRAINSABC/brainseg/BRAINSABCUtilities.cxx:115:13: warning: unused type alias 'ResampleIPFilterPointer' [-Wunused-local-typedef]
> /Users/johnsonhj/src/BRAINSTools/BRAINSCommonLib/TestSuite/ImgmathGTest.cxx:180:28: warning: lambda capture 'nimgs' is not required to be captured for this use [-Wunused-lambda-capture]
> /Users/johnsonhj/src/BRAINSTools/BRAINSCommonLib/TestSuite/itkIOGTest.cxx:156:69: warning: unused parameter 'y' [-Wunused-parameter]
> /Users/johnsonhj/src/BRAINSTools/BRAINSCommonLib/TestSuite/itkIOGTest.cxx:156:85: warning: unused parameter 'z' [-Wunused-parameter]
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[3](dcbytstr.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[4](dcchrstr.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[5](dccodec.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[6](dcdatset.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[10](dcdicent.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[11](dcdict.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[12](dcdictbi.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[13](dcdirrec.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[14](dcelem.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[16](dcerror.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[17](dcfilefo.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[19](dchashdi.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[20](dcistrma.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[21](dcistrmb.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[22](dcistrmf.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[23](dcistrms.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[25](dcitem.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[26](dcjson.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[27](dclist.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[28](dcmatch.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[29](dcmetinf.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[30](dcobject.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[31](dcostrma.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[33](dcostrmf.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[34](dcostrms.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[37](dcpcache.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[38](dcpixel.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[39](dcpixseq.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[40](dcpxitem.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[41](dcrleccd.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[43](dcrlecp.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[44](dcrledrg.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[47](dcsequen.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[48](dcspchrs.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[49](dcstack.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[50](dcswap.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[51](dctag.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[52](dctagkey.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[53](dctypes.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[54](dcuid.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[55](dcvr.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[56](dcvrae.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[57](dcvras.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[58](dcvrat.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[59](dcvrcs.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[60](dcvrda.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[61](dcvrds.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[62](dcvrdt.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[63](dcvrfd.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[64](dcvrfl.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[65](dcvris.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[66](dcvrlo.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[67](dcvrlt.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[68](dcvrobow.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[69](dcvrod.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[70](dcvrof.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[71](dcvrol.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[72](dcvrov.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[73](dcvrpn.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[74](dcvrpobw.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[75](dcvrsh.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[76](dcvrsl.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[77](dcvrss.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[78](dcvrst.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[79](dcvrsv.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[80](dcvrtm.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[81](dcvruc.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[82](dcvrui.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[83](dcvrul.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[84](dcvrulup.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[85](dcvrur.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[86](dcvrus.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[87](dcvrut.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[88](dcvruv.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[89](dcwcache.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[90](dcxfer.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[91](vrscan.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmdata.a[92](vrscanl.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmimage.a[3](diargimg.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmimage.a[4](dicmyimg.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmimage.a[5](dicoimg.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmimage.a[6](dicoopx.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmimage.a[7](dicopx.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmimage.a[8](dihsvimg.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmimage.a[9](dilogger.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmimage.a[10](dipalimg.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmimage.a[19](diregist.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmimage.a[20](dirgbimg.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmimage.a[21](diybrimg.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmimage.a[22](diyf2img.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmimage.a[23](diyp2img.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmimgle.a[2](dcmimage.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmimgle.a[3](dibaslut.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmimgle.a[6](didislut.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmimgle.a[7](didispfn.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmimgle.a[8](didocu.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmimgle.a[9](digsdfn.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmimgle.a[10](digsdlut.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmimgle.a[11](diimage.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmimgle.a[12](diinpx.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmimgle.a[13](diluptab.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmimgle.a[14](dimo1img.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmimgle.a[15](dimo2img.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmimgle.a[16](dimoimg.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmimgle.a[17](dimoimg3.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmimgle.a[18](dimoimg4.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmimgle.a[19](dimoimg5.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmimgle.a[20](dimomod.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmimgle.a[21](dimoopx.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmimgle.a[22](dimopx.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmimgle.a[23](diovdat.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmimgle.a[24](diovlay.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmimgle.a[25](diovlimg.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmimgle.a[26](diovpln.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmimgle.a[27](diutils.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmjpeg.a[4](djcodecd.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmjpeg.a[6](djcparam.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmjpeg.a[7](djdecbas.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmjpeg.a[8](djdecext.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmjpeg.a[9](djdeclol.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmjpeg.a[10](djdecode.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmjpeg.a[11](djdecpro.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmjpeg.a[12](djdecsps.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmjpeg.a[13](djdecsv1.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmjpeg.a[14](djdijg12.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmjpeg.a[15](djdijg8.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmjpeg.a[16](djdijg16.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libdcmjpeg.a[29](djutils.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg12.a[6](jccoefct.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg12.a[8](jcdctmgr.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg12.a[9](jcdiffct.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg12.a[10](jchuff.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg12.a[12](jclhuff.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg12.a[13](jclossls.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg12.a[14](jclossy.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg12.a[18](jcodec.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg12.a[19](jcomapi.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg12.a[21](jcphuff.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg12.a[22](jcpred.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg12.a[25](jcscale.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg12.a[26](jcshuff.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg12.a[28](jdapimin.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg12.a[29](jdapistd.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg12.a[33](jdcoefct.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg12.a[34](jdcolor.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg12.a[35](jddctmgr.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg12.a[36](jddiffct.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg12.a[37](jdhuff.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg12.a[38](jdinput.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg12.a[39](jdlhuff.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg12.a[40](jdlossls.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg12.a[41](jdlossy.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg12.a[42](jdmainct.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg12.a[43](jdmarker.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg12.a[44](jdmaster.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg12.a[45](jdmerge.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg12.a[46](jdphuff.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg12.a[47](jdpostct.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg12.a[48](jdpred.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg12.a[49](jdsample.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg12.a[50](jdscale.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg12.a[51](jdshuff.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg12.a[53](jerror.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg12.a[54](jfdctflt.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg12.a[55](jfdctfst.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg12.a[56](jfdctint.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg12.a[57](jidctflt.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg12.a[58](jidctfst.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg12.a[59](jidctint.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg12.a[60](jidctred.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg12.a[61](jmemmgr.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg12.a[62](jmemnobs.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg12.a[63](jquant1.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg12.a[64](jquant2.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg12.a[65](jutils.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg16.a[6](jccoefct.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg16.a[8](jcdctmgr.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg16.a[9](jcdiffct.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg16.a[10](jchuff.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg16.a[12](jclhuff.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg16.a[13](jclossls.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg16.a[14](jclossy.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg16.a[18](jcodec.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg16.a[19](jcomapi.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg16.a[21](jcphuff.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg16.a[22](jcpred.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg16.a[25](jcscale.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg16.a[26](jcshuff.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg16.a[28](jdapimin.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg16.a[29](jdapistd.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg16.a[33](jdcoefct.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg16.a[34](jdcolor.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg16.a[35](jddctmgr.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg16.a[36](jddiffct.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg16.a[37](jdhuff.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg16.a[38](jdinput.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg16.a[39](jdlhuff.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg16.a[40](jdlossls.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg16.a[41](jdlossy.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg16.a[42](jdmainct.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg16.a[43](jdmarker.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg16.a[44](jdmaster.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg16.a[45](jdmerge.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg16.a[46](jdphuff.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg16.a[47](jdpostct.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg16.a[48](jdpred.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg16.a[49](jdsample.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg16.a[50](jdscale.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg16.a[51](jdshuff.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg16.a[53](jerror.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg16.a[54](jfdctflt.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg16.a[55](jfdctfst.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg16.a[56](jfdctint.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg16.a[57](jidctflt.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg16.a[58](jidctfst.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg16.a[59](jidctint.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg16.a[60](jidctred.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg16.a[61](jmemmgr.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg16.a[62](jmemnobs.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg16.a[63](jquant1.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg16.a[64](jquant2.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg16.a[65](jutils.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg8.a[6](jccoefct.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg8.a[8](jcdctmgr.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg8.a[9](jcdiffct.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg8.a[10](jchuff.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg8.a[12](jclhuff.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg8.a[13](jclossls.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg8.a[14](jclossy.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg8.a[18](jcodec.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg8.a[19](jcomapi.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg8.a[21](jcphuff.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg8.a[22](jcpred.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg8.a[25](jcscale.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg8.a[26](jcshuff.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg8.a[28](jdapimin.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg8.a[29](jdapistd.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg8.a[33](jdcoefct.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg8.a[34](jdcolor.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg8.a[35](jddctmgr.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg8.a[36](jddiffct.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg8.a[37](jdhuff.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg8.a[38](jdinput.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg8.a[39](jdlhuff.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg8.a[40](jdlossls.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg8.a[41](jdlossy.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg8.a[42](jdmainct.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg8.a[43](jdmarker.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg8.a[44](jdmaster.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg8.a[45](jdmerge.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg8.a[46](jdphuff.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg8.a[47](jdpostct.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg8.a[48](jdpred.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg8.a[49](jdsample.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg8.a[50](jdscale.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg8.a[51](jdshuff.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg8.a[53](jerror.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg8.a[54](jfdctflt.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg8.a[55](jfdctfst.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg8.a[56](jfdctint.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg8.a[57](jidctflt.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg8.a[58](jidctfst.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg8.a[59](jidctint.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg8.a[60](jidctred.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg8.a[61](jmemmgr.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg8.a[62](jmemnobs.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg8.a[63](jquant1.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg8.a[64](jquant2.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libijg8.a[65](jutils.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboflog.a[2](apndimpl.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboflog.a[3](appender.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboflog.a[4](asyncap.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboflog.a[6](config.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboflog.a[7](consap.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboflog.a[9](env.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboflog.a[10](factory.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboflog.a[11](fileap.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboflog.a[12](fileinfo.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboflog.a[13](filter.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboflog.a[14](globinit.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboflog.a[15](hierarchy.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboflog.a[16](hierlock.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboflog.a[17](layout.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboflog.a[19](lockfile.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboflog.a[20](log4judp.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboflog.a[21](logevent.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboflog.a[22](logger.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboflog.a[23](logimpl.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboflog.a[24](loglevel.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboflog.a[25](loglog.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboflog.a[26](logmacro.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboflog.a[27](mdc.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboflog.a[28](ndc.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboflog.a[30](nullap.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboflog.a[31](objreg.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboflog.a[32](oflog.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboflog.a[33](patlay.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboflog.a[34](pointer.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboflog.a[35](property.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboflog.a[36](queue.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboflog.a[37](rootlog.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboflog.a[38](sleep.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboflog.a[39](snprintf.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboflog.a[40](sockbuff.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboflog.a[41](socket.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboflog.a[42](socketap.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboflog.a[45](strhelp.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboflog.a[47](syncprims.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboflog.a[48](syslogap.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboflog.a[49](threads.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboflog.a[50](timehelp.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboflog.a[53](unixsock.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libofstd.a[2](ofchrenc.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libofstd.a[3](ofcmdln.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libofstd.a[4](ofconapp.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libofstd.a[5](ofcond.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libofstd.a[7](ofconsol.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libofstd.a[9](ofdate.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libofstd.a[10](ofdatime.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libofstd.a[11](oferror.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libofstd.a[12](offile.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libofstd.a[13](offilsys.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libofstd.a[16](oflist.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libofstd.a[17](ofstd.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libofstd.a[18](ofstring.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libofstd.a[20](ofthread.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libofstd.a[21](oftime.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libofstd.a[22](oftimer.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libofstd.a[25](ofuuid.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libofstd.a[26](ofmath.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/libofstd.a[28](ofrand.cc.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboficonv.a[2](citrus_bcs.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboficonv.a[3](citrus_bcs_strtol.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboficonv.a[4](citrus_bcs_strtoul.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboficonv.a[5](citrus_big5.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboficonv.a[6](citrus_csmapper.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboficonv.a[7](citrus_db.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboficonv.a[9](citrus_db_hash.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboficonv.a[10](citrus_dechanyu.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboficonv.a[11](citrus_esdb.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboficonv.a[12](citrus_euc.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboficonv.a[13](citrus_euctw.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboficonv.a[14](citrus_gbk2k.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboficonv.a[15](citrus_hash.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboficonv.a[16](citrus_hz.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboficonv.a[17](citrus_iconv.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboficonv.a[18](citrus_iconv_none.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboficonv.a[19](citrus_iconv_std.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboficonv.a[20](citrus_iso2022.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboficonv.a[21](citrus_jisx0208.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboficonv.a[22](citrus_johab.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboficonv.a[23](citrus_lookup.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboficonv.a[25](citrus_mapper_646.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboficonv.a[26](citrus_mapper.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboficonv.a[27](citrus_mapper_none.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboficonv.a[28](citrus_mapper_serial.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboficonv.a[29](citrus_mapper_std.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboficonv.a[30](citrus_mapper_zone.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboficonv.a[31](citrus_memstream.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboficonv.a[32](citrus_mmap.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboficonv.a[33](citrus_module.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboficonv.a[34](citrus_mskanji.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboficonv.a[35](citrus_none.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboficonv.a[37](citrus_prop.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboficonv.a[38](citrus_stdenc.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboficonv.a[39](citrus_ues.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboficonv.a[40](citrus_utf1632.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboficonv.a[41](citrus_utf7.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboficonv.a[42](citrus_utf8.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboficonv.a[43](citrus_viqr.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboficonv.a[44](citrus_zw.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboficonv.a[45](oficonv_iconv.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboficonv.a[46](oficonv_logger.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboficonv.a[49](data_esdb.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> ld: warning: object file (/Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-5.8.0/lib/liboficonv.a[50](data_csmapper.c.o)) was built for newer 'macOS' version (26.6) than being linked (15.0)
> /Users/johnsonhj/src/BRAINSTools/BRAINSABC/brainseg/GeneratePurePlugMask.cxx:51:9: warning: unused type alias 'LocalReaderPointer' [-Wunused-local-typedef]
> /Users/johnsonhj/src/BRAINSTools/BRAINSABC/brainseg/BRAINSABC.cxx:574:17: warning: unused type alias 'LocalReaderPointer' [-Wunused-local-typedef]
> /Users/johnsonhj/src/BRAINSTools/BRAINSABC/brainseg/BRAINSABC.cxx:679:17: warning: unused type alias 'LocalReaderPointer' [-Wunused-local-typedef]
> /Users/johnsonhj/src/BRAINSTools/BRAINSABC/brainseg/BRAINSABC.cxx:957:17: warning: unused type alias 'ResamplePointer' [-Wunused-local-typedef]
> /Users/johnsonhj/src/BRAINSTools/BRAINSABC/brainseg/BRAINSABC.cxx:1072:13: warning: unused type alias 'LocalReaderPointer' [-Wunused-local-typedef]
> /Users/johnsonhj/src/BRAINSTools/BRAINSABC/brainseg/BRAINSABC.cxx:230:9: warning: unused type alias 'ReaderPointer' [-Wunused-local-typedef]
> /Users/johnsonhj/src/BRAINSTools/BRAINSSnapShotWriter/BRAINSSnapShotWriter.cxx:146:9: warning: unused type alias 'ReaderPointer' [-Wunused-local-typedef]
> ld: warning: object file (/opt/homebrew/Cellar/googletest/1.18.0/lib/libgtest_main.a[2](gtest_main.cc.o)) was built for newer 'macOS' version (26.0) than being linked (15.0)
> ld: warning: object file (/opt/homebrew/Cellar/googletest/1.18.0/lib/libgtest.a[2](gtest-all.cc.o)) was built for newer 'macOS' version (26.0) than being linked (15.0)

## ctest

- Result: T:553/554
- Baseline: /Users/johnsonhj/src/itk_forest_build_testbed/.devlocal/init-over-assign/baselines/BRAINSTools-standalone-60b069efa67222a2adbdd1ce757ca4a2bd462210-af229066.json
- No new failures against the baseline.

## Notes

- llvm: /opt/homebrew/opt/llvm/bin (clang-tidy 23.1.4); tidy-series: skipped (AppleClang 21.0.0 vs clang-tidy 23.1.4)
- baseline build: rebuilt /Users/johnsonhj/src/BRAINSTools/build/BRAINSTools-Release-EPRelease-build at 60b069efa672 before the baseline ctest
- local-const: 2 plain auto local(s) near a prior site left unanalyzed
- itk-helpers-constexpr: 5 plain auto local(s) near a prior site left unanalyzed

## Operator verification

Repo: BRAINSia/BRAINSTools (60b069ef) | Standalone: ~/src/BRAINSTools,
build build/BRAINSTools-Release-EPRelease-build. Kit cf87e46, run from a
plain shell (`env -i`, no pixi) on 2026-10-27 19:26 to 19:54 CDT, exit 0.

### Run checks

- The dry run printed `llvm: /opt/homebrew/opt/llvm/bin (clang-tidy
  23.1.4)` and the AppleClang tidy-series note, and exited 0.
- The baseline was re-measured after the pre-baseline ninja. One test
  already failed there (`BCDTest_writeBranded2DImage`), and the final
  ctest of 553/554 has no new failure.
- After the run, `otool -L` on `ImgmathGTest` and
  `libgtractInvertRigidTransformLib.dylib` names `/usr/lib/libc++.1.dylib`.
- No file under `build/` changed during the run: no installed header in
  `build/BRAINSTools-Release-5.8.0/include` and no source-like file
  elsewhere under `build/`. The stages edited only tracked files.
- `git log main..HEAD` shows 8 commits in stage order with the design's
  subjects. container-list-init has no commit of its own (see concern 3).
  The diffstat is 83 files, +297/-442. The working tree is clean.
- Comment lines: 4 removed and 5 added. The extra one is
  `// Allow blurring if distance from edge`, moved from a trailing comment
  to its own line (`BRAINSDeface/BRAINSDeface.cxx:281`). No comment was
  lost.
- `pre-commit run --all-files` in the checkout, after the master's own
  pre-commit step: exit 0, no file changed. BRAINSTools pins
  mirrors-clang-format v19.1.7. Homebrew clang-format 23.1.4 with
  `--dry-run -Werror` also reports 0 violations on all 83 changed files.
- Pointer check: no added line gives `{}` or `{nullptr}` to a member whose
  type contains `Pointer`, `unique_ptr`, `shared_ptr`, or `SmartPointer`.
  member-default-init's only site is
  `DWIConvert/brainsDCMTKFileReader.h:526`
  (`std::string m_FileName{}`). The `std::unique_ptr<DcmFileFormat>
  m_DFile;` beside it is untouched.
- `BRAINSABC/brainseg/LLSBiasCorrector.hxx` is not in the member-init
  commit. Both of its sites (lines 78 and 81) were reverted as
  gate-failed, and the file is byte-identical to main, so the revert was
  clean. The reverted proposal, kept in `refs/ioa/backup/member-init`, is a
  valid initializer list (`m_DebugLevel`, `m_OutputDebugDir`,
  `m_MaxDegree`, `m_SampleSpacing`).

### Diffs read in full

I read member-init, member-default-init, local-init, local-const,
container-const, itk-helpers, itk-helpers-constexpr, and narrow-scope.
**No behavior change was found.** Initializer lists follow declaration
order with base initializers first. The `m_CurvatureThreshold` family
belongs to the derived Dti*TrackingFilter classes, and those templates are
instantiated in `GTRACT/Cmdline/gtractFiberTracking.cxx`. Every
narrow-scope move keeps evaluation order. The build carries `-Wshadow`,
and no moved name is used outside its new scope.

Questionable but not behavior-changing:

1. `BRAINSDeface/BRAINSDeface.cxx:89` (narrow-scope). The brace-line
   comment `{ // Generate a new mask` became a trailing comment on a moved
   declaration: `constexpr int outside_fov = 3; // Generate a new mask`.
2. `BRAINSConstellationDetector/src/landmarksConstellationDetector.cxx`
   (itk-helpers). `AllocateInitialized(); // true implies ...FillBuffer(0);`
   keeps a trailing comment that refers to the removed `true` argument.
   This happens twice (roiImage, roiMask).
3. Hunk ownership goes to the later stage, so the list-init rewrites
   (`push_back` runs to braces) ship inside the container-const commit
   "Make list-initialized containers const where never mutated". The
   itk-helpers-constexpr commit likewise carries `Fill` to `Filled` and
   `const` hunks. The subjects understate the content.
4. narrow-scope moves a declaration into a loop or `if` after local-init
   has run, so it leaves declare-then-assign pairs that local-init would
   have merged:
   `GTRACT/Common/itkEigenVectorToColorImageFilter.cxx:76`,
   `GTRACT/Common/itkTensorToAnisotropyImageFilter.cxx:111,132`,
   `BRAINSConstellationDetector/src/landmarksDataSet.h:103`,
   `BRAINSConstellationDetector/src/BRAINSLmkTransform.cxx:270`,
   `BRAINSConstellationDetector/landmarkStatistics/LmkStatistics.cxx:121`.
5. About 15 GTRACT and BRAINSMush tools now read
   `if (bool debug = true; debug)`, a constant condition moved into an
   if-init. It is legal, but reviewers are likely to object.
6. `DWIConvert/TestSuite/DWICompare.cxx:139`. The commented-out
   gradient-tolerance block moved with `bValueTolerance` and now sits on an
   unrelated `if`. `itkDivergenceImageFilter.h:380` swaps the order of two
   comments.
7. Cosmetic: doubled blank lines at
   `DWIConvert/TestSuite/NrrdToNIfTI.cxx:42` and
   `BRAINSSuperResolution/EdgeBasedWeightedTV/itkDivergenceImageFilter.h:321`.
   The `std::string m_FileName{}` default initializer is redundant.

### Gate false rejections

There were 120 gate-failed skips, many "not attributed to a staged file".
Running `skills/itk-compile-gate.sh` on unchanged sources
(`BRAINSABC/brainseg/BRAINSABC.cxx`, `GeneratePurePlugMask.cxx`) fails
the same way on main: `error: unused type alias 'LocalReaderPointer'
[-Werror,-Wunused-local-typedef]` at `BRAINSABC.cxx:574` and
`GeneratePurePlugMask.cxx:51`. The gate's fatal warning set turns
pre-existing warnings in including translation units into failures, so
valid sites are reverted. That lowers yield but does not make the output
wrong. The run directory keeps no gate log, so each reason has to be
reproduced by hand.

### Comparison with PR #645

The same heuristic hunk classifier was run on both diffs. A hunk can
count toward more than one kind.

| Kind | #645 | this branch |
|---|---|---|
| hunks / files | 462 / 150 | 142 / 83 |
| narrow-scope moves | 101 | 10 + ~60 if/switch-init |
| container list-init | 75 | 17 |
| local declare-then-init | 57 | 16 |
| member init (ctor) | 49 | 17 |
| sized ctor | 40 | 0 |
| placeholder merge | 34 | 2 |
| `Fill(x)` into ctor arg | 20 | 0 |
| ITK helpers | 17 | 7 |
| stream open | 12 | 7 |
| loop variable into `for` | 11 | 0 |
| if/else into ternary | 8 | 0 to 1 |
| `SetIdentity` to `GetIdentity` | 5 | 0 |
| `operator=` into copy ctor | 2 | 0 |

Present in #645 and absent here: sized ctor, `Fill(x)` into a ctor value
argument, loop variable into `for`, if/else into ternary,
`SetIdentity`/`GetIdentity`, and `operator=` into a copy ctor. The first
two are named stage-2 classes, so their zero is a yield question for
sized_ctor. The rest have no stage. The lower counts elsewhere come from
conservative skips (costly-construct 297, loop-carried 231,
try-read-after 63) and from the 120 gate false rejections. The earlier
classification of #645 noted two items that still apply to that PR:
`AtlasCropImageSource.hxx` drops `Fill(0)` calls without visible
replacements, and `genericRegistrationHelper.hxx` redeclares
`unsigned long m` in five branches.

### Left in the checkout

The checkout is on branch `style-init-over-assign-20261027` at d781bcf0.
Eight `refs/ioa/backup/*` refs remain (member-init, member-default-init,
local-init, local-const, container-const, itk-helpers,
itk-helpers-constexpr, narrow-scope). The master does not remove them
after a green run. Nothing was pushed.
